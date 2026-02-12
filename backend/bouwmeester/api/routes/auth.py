"""Auth routes -- OIDC login/callback/logout/status/onboarding/access requests."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from datetime import date
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import (
    CurrentUser,
    get_oauth,
    get_or_create_person,
    revoke_tokens,
    validate_session_token,
)
from bouwmeester.core.config import Settings, get_settings
from bouwmeester.core.database import get_db
from bouwmeester.core.whitelist import is_email_allowed
from bouwmeester.models.access_request import AccessRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.schema.access_request import (
    AccessRequestCreate,
    AccessRequestStatusResponse,
)
from bouwmeester.schema.person import (
    OnboardingRequest,
    PersonDetailResponse,
    PersonResponse,
)
from bouwmeester.services.merge import find_merge_candidates, merge_persons
from bouwmeester.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# In-memory rate limiter for auth endpoints (login/callback/logout only)
# ---------------------------------------------------------------------------

_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 30  # requests per window per IP
_RATE_LIMIT_MAX_KEYS = 10_000  # max tracked IPs (LRU eviction)
_rate_limit_store: OrderedDict[str, list[float]] = OrderedDict()


def _get_client_ip(request: Request) -> str:
    """Extract the client IP from the ASGI connection.

    We intentionally do NOT trust X-Forwarded-For here because any client can
    spoof that header.  The reverse proxy (nginx / k8s ingress) should be
    configured to set the real remote address on the ASGI connection instead
    (e.g. uvicorn ``--proxy-headers`` with ``--forwarded-allow-ips``).
    """
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    """Raise 429 if the client IP has exceeded the rate limit."""
    client_ip = _get_client_ip(request)
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW

    # Prune old entries for this IP.
    timestamps = _rate_limit_store.get(client_ip, [])
    pruned = [t for t in timestamps if t > window_start]

    if len(pruned) >= _RATE_LIMIT_MAX:
        _rate_limit_store[client_ip] = pruned
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
        )

    pruned.append(now)
    _rate_limit_store[client_ip] = pruned
    _rate_limit_store.move_to_end(client_ip)

    # Evict oldest entries if we exceed the max tracked keys.
    while len(_rate_limit_store) > _RATE_LIMIT_MAX_KEYS:
        _rate_limit_store.popitem(last=False)


# ---------------------------------------------------------------------------
# GET /login -- redirect to Keycloak authorization page
# ---------------------------------------------------------------------------


@router.get("/login")
async def login(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the user to the OIDC provider login page."""
    _check_rate_limit(request)
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC is not configured",
        )

    # Build callback URI from settings to prevent Host header manipulation.
    backend_url = settings.BACKEND_URL
    redirect_uri = f"{backend_url}/api/auth/callback"
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


# ---------------------------------------------------------------------------
# GET /callback -- handle OIDC redirect after login
# ---------------------------------------------------------------------------


@router.get("/callback")
async def callback(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Handle the OIDC callback.

    Exchanges the authorization code for tokens, stores them in the
    server-side session, and redirects the user to the frontend.
    """
    _check_rate_limit(request)
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC is not configured",
        )

    token = await oauth.keycloak.authorize_access_token(request)

    # Rotate the session ID to prevent session fixation attacks.
    # Clear the old session and populate a fresh one (the session middleware
    # will detect the clear + re-population and issue a new session ID).
    session = request.session
    session.clear()

    session["access_token"] = token.get("access_token")
    session["refresh_token"] = token.get("refresh_token")
    session["id_token"] = token.get("id_token")
    # Mark session as needing a new ID (picked up by session middleware).
    session["_rotate"] = True

    # Extract user info for quick access.
    userinfo = token.get("userinfo", {})
    if userinfo:
        session["person_sub"] = userinfo.get("sub", "")
        session["person_email"] = userinfo.get("email", "")
        session["person_name"] = userinfo.get(
            "name", userinfo.get("preferred_username", "")
        )

    logger.info("OIDC login successful for %s", session.get("person_email", "?"))

    return RedirectResponse(url=settings.FRONTEND_URL, status_code=302)


# ---------------------------------------------------------------------------
# GET /logout -- clear session and redirect to Keycloak logout
# ---------------------------------------------------------------------------


@router.get("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Clear local session state and redirect to the OIDC end-session endpoint."""
    _check_rate_limit(request)
    id_token = request.session.get("id_token")
    access_token = request.session.get("access_token")
    refresh_token = request.session.get("refresh_token")

    # Clear all session data.
    request.session.clear()

    if not settings.OIDC_ISSUER:
        return RedirectResponse(url=settings.FRONTEND_URL, status_code=302)

    # Best-effort token revocation (don't block logout on failure).
    await revoke_tokens(
        settings=settings,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    # Build the OIDC end-session URL.
    end_session_url = (
        f"{settings.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/logout"
    )

    params: dict[str, str] = {
        "post_logout_redirect_uri": settings.FRONTEND_URL,
        "client_id": settings.OIDC_CLIENT_ID,
    }
    if id_token:
        params["id_token_hint"] = id_token

    return RedirectResponse(
        url=f"{end_session_url}?{urlencode(params)}", status_code=302
    )


# ---------------------------------------------------------------------------
# Helper: check whether a person still needs onboarding
# ---------------------------------------------------------------------------


async def _check_needs_onboarding(db: AsyncSession, person: Person) -> bool:
    """Return True if the person is missing functie or an active org placement."""
    if not person.functie:
        return True
    stmt = select(PersonOrganisatieEenheid.id).where(
        PersonOrganisatieEenheid.person_id == person.id,
        PersonOrganisatieEenheid.eind_datum.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# GET /status -- check auth status (used by frontend on load)
# ---------------------------------------------------------------------------


@router.get("/status")
async def auth_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return authentication status for the current session."""
    # No rate limit here — this is called on every page load by the frontend.
    oidc_configured = bool(settings.OIDC_ISSUER)
    authenticated = False

    if request.session.get("access_token") and oidc_configured:
        authenticated = await validate_session_token(request.session, settings)

    result: dict = {
        "authenticated": authenticated,
        "oidc_configured": oidc_configured,
    }

    if authenticated:
        sub = request.session.get("person_sub", "")
        email = request.session.get("person_email", "")
        name = request.session.get("person_name", "")

        if not is_email_allowed(email):
            logger.warning("Access denied for %s — not on whitelist", email)
            request.session.clear()
            return {
                "authenticated": False,
                "oidc_configured": oidc_configured,
                "access_denied": True,
                "denied_email": email,
            }

        # Use cached values from session to avoid DB queries on every page load.
        person_id = request.session.get("person_db_id")
        needs_onboarding = request.session.get("needs_onboarding")

        is_admin = request.session.get("is_admin")

        # Resolve from DB on first call.
        if person_id is None and sub and email:
            person = await get_or_create_person(db, sub=sub, email=email, name=name)
            person_id = str(person.id)
            needs_onboarding = await _check_needs_onboarding(db, person)
            is_admin = person.is_admin

            # Cache in session.
            request.session["person_db_id"] = person_id
            request.session["needs_onboarding"] = needs_onboarding
            request.session["is_admin"] = is_admin
        elif person_id is not None:
            # Re-fetch is_admin from DB periodically so admin-role changes
            # take effect without requiring the target user to re-login.
            # Throttled to at most once per 60s to avoid a DB query on every
            # page load.
            last_check = request.session.get("is_admin_checked_at", 0)
            if time.time() - last_check > 60:
                person_obj = await db.get(Person, UUID(person_id))
                if person_obj is not None:
                    is_admin = person_obj.is_admin
                    request.session["is_admin"] = is_admin
                request.session["is_admin_checked_at"] = time.time()

        result["person"] = {
            "sub": sub,
            "email": email,
            "name": name,
            "id": person_id,
            "needs_onboarding": bool(needs_onboarding),
            "is_admin": bool(is_admin),
        }

    return result


# ---------------------------------------------------------------------------
# GET /me -- return the currently authenticated user
# ---------------------------------------------------------------------------


@router.get("/me", response_model=PersonDetailResponse)
async def me(current_user: CurrentUser) -> PersonDetailResponse:
    """Return information about the currently authenticated user."""
    return PersonDetailResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# GET /merge-candidates -- find potential duplicate persons
# ---------------------------------------------------------------------------


@router.get("/merge-candidates", response_model=list[PersonResponse])
async def get_merge_candidates(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[PersonResponse]:
    """Find persons that may be duplicates of the current user."""
    candidates = await find_merge_candidates(db, current_user)
    return [PersonResponse.model_validate(c) for c in candidates]


# ---------------------------------------------------------------------------
# POST /onboarding -- complete onboarding for a new SSO user
# ---------------------------------------------------------------------------


@router.post("/onboarding", response_model=PersonDetailResponse)
async def complete_onboarding(
    request: Request,
    body: OnboardingRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> PersonDetailResponse:
    """Complete the onboarding flow for a newly-created SSO user.

    Updates the person's name and functie, and creates an org placement.
    If merge_with_id is provided, merges the current stub into the existing
    person. Rejects the request if the user has already completed onboarding.
    """
    # Guard: reject if already onboarded.
    if not await _check_needs_onboarding(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding is al voltooid",
        )

    if body.merge_with_id:
        # Merge: absorb current stub into the existing person
        target = await db.get(Person, body.merge_with_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Samenvoeg-persoon niet gevonden",
            )
        merged = await merge_persons(
            db,
            keep_id=body.merge_with_id,
            absorb_id=current_user.id,
        )

        # Update session to point to the merged person
        request.session["person_db_id"] = str(merged.id)
        request.session.pop("needs_onboarding", None)

        return PersonDetailResponse.model_validate(merged)

    # Non-merge path: org is required.
    if not body.organisatie_eenheid_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Organisatie-eenheid is verplicht",
        )

    # Validate that the org unit exists.
    org_stmt = select(OrganisatieEenheid.id).where(
        OrganisatieEenheid.id == body.organisatie_eenheid_id
    )
    org_result = await db.execute(org_stmt)
    if org_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Organisatie-eenheid niet gevonden",
        )

    current_user.naam = body.naam
    current_user.functie = body.functie

    # Create org placement (start today)
    placement = PersonOrganisatieEenheid(
        person_id=current_user.id,
        organisatie_eenheid_id=body.organisatie_eenheid_id,
        dienstverband=body.dienstverband,
        start_datum=date.today(),
    )
    db.add(placement)
    await db.flush()
    await db.refresh(current_user)

    # Invalidate the session cache so /status re-checks from DB.
    request.session.pop("needs_onboarding", None)
    request.session.pop("person_db_id", None)

    return PersonDetailResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# POST /request-access -- submit an access request (public, rate-limited)
# ---------------------------------------------------------------------------

# Separate rate limiter for access requests (stricter)
_ACCESS_REQUEST_RATE_LIMIT_WINDOW = 300  # 5 minutes
_ACCESS_REQUEST_RATE_LIMIT_MAX = 5  # requests per window per IP
_access_request_rate_store: OrderedDict[str, list[float]] = OrderedDict()


def _check_access_request_rate_limit(request: Request) -> None:
    """Raise 429 if the client IP has exceeded the access request rate limit."""
    client_ip = _get_client_ip(request)
    now = time.monotonic()
    window_start = now - _ACCESS_REQUEST_RATE_LIMIT_WINDOW

    timestamps = _access_request_rate_store.get(client_ip, [])
    pruned = [t for t in timestamps if t > window_start]

    if len(pruned) >= _ACCESS_REQUEST_RATE_LIMIT_MAX:
        _access_request_rate_store[client_ip] = pruned
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Te veel verzoeken, probeer het later opnieuw",
        )

    pruned.append(now)
    _access_request_rate_store[client_ip] = pruned
    _access_request_rate_store.move_to_end(client_ip)

    while len(_access_request_rate_store) > _RATE_LIMIT_MAX_KEYS:
        _access_request_rate_store.popitem(last=False)


@router.post("/request-access", response_model=AccessRequestStatusResponse)
async def request_access(
    request: Request,
    body: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> AccessRequestStatusResponse:
    """Submit an access request. Public endpoint (no auth required)."""
    _check_access_request_rate_limit(request)

    email = body.email.strip().lower()

    # If already on whitelist, tell the user
    if is_email_allowed(email):
        return AccessRequestStatusResponse(
            has_pending=False,
            status="already_allowed",
        )

    # Check for existing pending request
    existing = await db.execute(
        select(AccessRequest).where(
            AccessRequest.email == email,
            AccessRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return AccessRequestStatusResponse(
            has_pending=True,
            status="already_pending",
        )

    # Create the request — the partial unique index on (email) WHERE status='pending'
    # prevents duplicates at the DB level even under concurrent requests.
    access_request = AccessRequest(email=email, naam=body.naam)
    db.add(access_request)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return AccessRequestStatusResponse(
            has_pending=True,
            status="already_pending",
        )

    # Notify admins
    notification_service = NotificationService(db)
    await notification_service.notify_access_request(email, body.naam)

    return AccessRequestStatusResponse(
        has_pending=True,
        status="pending",
    )


# ---------------------------------------------------------------------------
# GET /access-request-status -- check status of an access request (public)
# ---------------------------------------------------------------------------


@router.get("/access-request-status", response_model=AccessRequestStatusResponse)
async def access_request_status(
    email: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> AccessRequestStatusResponse:
    """Check the status of the latest access request for an email."""
    email = email.strip().lower()

    # If already on whitelist, they're allowed now
    if is_email_allowed(email):
        return AccessRequestStatusResponse(
            has_pending=False,
            status="approved",
        )

    # Find the most recent request for this email
    result = await db.execute(
        select(AccessRequest)
        .where(AccessRequest.email == email)
        .order_by(AccessRequest.requested_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if latest is None:
        return AccessRequestStatusResponse(
            has_pending=False,
            status=None,
        )

    return AccessRequestStatusResponse(
        has_pending=latest.status == "pending",
        status=latest.status,
        deny_reason=latest.deny_reason,
    )
