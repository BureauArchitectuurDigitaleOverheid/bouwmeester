"""Auth routes -- OIDC login / callback / logout / status / me / onboarding."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
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
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.schema.person import OnboardingRequest, PersonDetailResponse

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

        # Use cached values from session to avoid DB queries on every page load.
        person_id = request.session.get("person_db_id")
        needs_onboarding = request.session.get("needs_onboarding")

        # Resolve from DB only on first call (or after cache invalidation).
        if person_id is None and sub and email:
            person = await get_or_create_person(db, sub=sub, email=email, name=name)
            person_id = str(person.id)
            needs_onboarding = await _check_needs_onboarding(db, person)

            # Cache in session.
            request.session["person_db_id"] = person_id
            request.session["needs_onboarding"] = needs_onboarding

        result["person"] = {
            "sub": sub,
            "email": email,
            "name": name,
            "id": person_id,
            "needs_onboarding": bool(needs_onboarding),
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
    Rejects the request if the user has already completed onboarding.
    """
    # Guard: reject if already onboarded.
    if not await _check_needs_onboarding(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onboarding is al voltooid",
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
