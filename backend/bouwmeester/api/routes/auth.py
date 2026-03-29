"""Auth routes -- OIDC login/callback/logout/status/onboarding/access requests."""

from __future__ import annotations

import logging
import time
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
    is_webauthn_session,
    is_webauthn_session_expired,
    revoke_tokens,
    validate_session_token,
)
from bouwmeester.core.config import Settings, get_settings
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import build_org_context
from bouwmeester.core.query_utils import normalize_email
from bouwmeester.core.rate_limit import InMemoryRateLimiter
from bouwmeester.core.whitelist import is_email_allowed
from bouwmeester.models.access_request import AccessRequest
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.repositories.person import PersonRepository
from bouwmeester.schema.access_request import (
    AccessRequestCreate,
    AccessRequestStatusResponse,
)
from bouwmeester.schema.person import (
    OnboardingRequest,
    PersonDetailResponse,
)
from bouwmeester.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limiter for auth endpoints (login/callback/logout).
_rate_limiter = InMemoryRateLimiter(window=60, max_requests=30)


# ---------------------------------------------------------------------------
# GET /login -- redirect to Keycloak authorization page
# ---------------------------------------------------------------------------


@router.get("/login")
async def login(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the user to the OIDC provider login page."""
    _rate_limiter.check(request)
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
    _rate_limiter.check(request)
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
    _rate_limiter.check(request)
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


def _check_needs_onboarding(person: Person) -> bool:
    """Return True if the person has not yet completed the onboarding form.

    Onboarding is considered complete once the person has a functie set.
    Whether they have an active org placement is tracked separately via
    ``needs_placement`` / ``has_pending_placement``.
    """
    return not person.functie


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

    # WebAuthn-only sessions have no OIDC tokens — the session itself is
    # the sole authentication mechanism (bounded by session TTL).
    # We must verify the person is still active since this endpoint is on a
    # public prefix and skips the auth middleware entirely.
    webauthn_session = False
    if is_webauthn_session(request.session):
        ttl = settings.WEBAUTHN_SESSION_TTL_SECONDS
        if is_webauthn_session_expired(request.session, ttl):
            request.session.clear()
        else:
            try:
                person_obj = await db.get(Person, UUID(request.session["person_db_id"]))
                if person_obj is not None and person_obj.is_active:
                    authenticated = True
                    webauthn_session = True
                else:
                    # Person deactivated — clear the stale session.
                    request.session.clear()
            except Exception:
                request.session.clear()
    else:
        try:
            if request.session.get("access_token") and oidc_configured:
                authenticated = await validate_session_token(request.session, settings)
        except Exception:
            logger.exception("Token validation failed in auth_status")
            authenticated = False
            return {
                "authenticated": False,
                "oidc_configured": oidc_configured,
                "error": "token_validation_failed",
            }

    result: dict = {
        "authenticated": authenticated,
        "oidc_configured": oidc_configured,
        "webauthn_session": webauthn_session,
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

        try:
            from bouwmeester.core.permissions import build_permission_context

            # Use cached values from session to avoid DB queries on every
            # page load.
            person_id = request.session.get("person_db_id")
            needs_onboarding = request.session.get("needs_onboarding")

            is_admin = request.session.get("is_admin")
            perm_ctx = None  # reused below for roles/permissions

            # Resolve from DB on first call.
            if person_id is None and sub and email:
                person = await get_or_create_person(db, sub=sub, email=email, name=name)
                person_id = str(person.id)
                needs_onboarding = _check_needs_onboarding(person)

                perm_ctx = await build_permission_context(db, person)
                is_admin = perm_ctx.is_super_admin

                # Cache in session.
                request.session["person_db_id"] = person_id
                request.session["needs_onboarding"] = needs_onboarding
                request.session["is_admin"] = is_admin
            elif person_id is not None:
                # Re-fetch is_admin from RBAC periodically so admin-role
                # changes take effect without requiring the target user to
                # re-login.  Throttled to at most once per 60s to avoid a
                # DB query on every page load.
                last_check = request.session.get("is_admin_checked_at", 0)
                if time.time() - last_check > 60:
                    person_obj = await db.get(Person, UUID(person_id))
                    if person_obj is not None:
                        perm_ctx = await build_permission_context(db, person_obj)
                        is_admin = perm_ctx.is_super_admin
                        request.session["is_admin"] = is_admin
                    request.session["is_admin_checked_at"] = time.time()

            # Fetch org eenheid info for the person
            org_eenheden: list[dict] = []
            managed_eenheden_list: list[dict] = []
            needs_placement = False
            has_pending_placement = False
            placement_denied = False
            if person_id:
                pid = UUID(person_id)
                # Own placements (active)
                placement_stmt = (
                    select(
                        OrganisatieEenheid.id,
                        OrganisatieEenheid.naam,
                        OrganisatieEenheid.type,
                    )
                    .join(
                        PersonOrganisatieEenheid,
                        PersonOrganisatieEenheid.organisatie_eenheid_id
                        == OrganisatieEenheid.id,
                    )
                    .where(
                        PersonOrganisatieEenheid.person_id == pid,
                        PersonOrganisatieEenheid.eind_datum.is_(None),
                    )
                )
                placement_result = await db.execute(placement_stmt)
                org_eenheden = [
                    {"id": str(r.id), "naam": r.naam, "type": r.type}
                    for r in placement_result.all()
                ]
                needs_placement = len(org_eenheden) == 0

                # Check for pending/denied placement request
                if needs_placement:
                    latest_req_stmt = (
                        select(
                            OrgPlacementRequest.status,
                        )
                        .where(
                            OrgPlacementRequest.person_id == pid,
                        )
                        .order_by(OrgPlacementRequest.requested_at.desc())
                        .limit(1)
                    )
                    latest_req_result = await db.execute(latest_req_stmt)
                    latest_req = latest_req_result.scalar_one_or_none()
                    if latest_req == "pending":
                        has_pending_placement = True
                    elif latest_req == "denied":
                        placement_denied = True

            # Build org context once — derives managed eenheden and
            # visible eenheid IDs without duplicate queries.
            visible_eenheid_ids_list: list[str] = []
            org_ctx = None
            if person_id:
                person_for_org = await db.get(Person, UUID(person_id))
                if person_for_org:
                    org_ctx = await build_org_context(
                        db, person_for_org, perm_ctx=perm_ctx
                    )

                    if org_ctx.is_admin:
                        visible_eenheid_ids_list = ["*"]
                    else:
                        visible_eenheid_ids_list = [
                            str(eid)
                            for eid in set(
                                org_ctx.visible_eenheid_ids + org_ctx.shared_eenheid_ids
                            )
                        ]

                    # Managed eenheden details (from org context)
                    if org_ctx.managed_eenheid_ids:
                        managed_detail_stmt = select(
                            OrganisatieEenheid.id,
                            OrganisatieEenheid.naam,
                            OrganisatieEenheid.type,
                        ).where(OrganisatieEenheid.id.in_(org_ctx.managed_eenheid_ids))
                        managed_detail_result = await db.execute(managed_detail_stmt)
                        managed_eenheden_list = [
                            {"id": str(r.id), "naam": r.naam, "type": r.type}
                            for r in managed_detail_result.all()
                        ]

            # Resolve RBAC roles and permissions
            roles_list: list[dict] = []
            permissions_list: list[str] = []
            scoped_permissions_dict: dict[str, list[str]] = {}
            if person_id:
                from bouwmeester.repositories.role import (
                    PersonRoleRepository,
                )

                pid_uuid = UUID(person_id)
                # Reuse perm_ctx if already built above, otherwise build it
                if perm_ctx is None:
                    person_for_perm = await db.get(Person, pid_uuid)
                    if person_for_perm:
                        perm_ctx = await build_permission_context(db, person_for_perm)
                if perm_ctx is not None:
                    permissions_list = sorted(perm_ctx.effective_permissions)
                    if not perm_ctx.is_super_admin:
                        scoped_permissions_dict = {
                            str(eid): sorted(perms)
                            for eid, perms in perm_ctx.scoped_permissions.items()
                        }

                    pr_repo = PersonRoleRepository(db)
                    assignments = await pr_repo.list_for_person(pid_uuid)
                    roles_list = [
                        {
                            "role_id": a.role_id,
                            "role_naam": (a.role.naam if a.role else None),
                            "organisatie_eenheid_id": (
                                str(a.organisatie_eenheid_id)
                                if a.organisatie_eenheid_id
                                else None
                            ),
                            "eenheid_naam": (
                                a.organisatie_eenheid.naam
                                if a.organisatie_eenheid
                                else None
                            ),
                        }
                        for a in assignments
                    ]

            result["person"] = {
                "sub": sub,
                "email": email,
                "name": name,
                "id": person_id,
                "needs_onboarding": bool(needs_onboarding),
                "is_admin": bool(is_admin),
                "organisatie_eenheden": org_eenheden,
                "managed_eenheden": managed_eenheden_list,
                "needs_placement": needs_placement,
                "has_pending_placement": has_pending_placement,
                "placement_denied": placement_denied,
                "roles": roles_list,
                "permissions": permissions_list,
                "visible_eenheid_ids": visible_eenheid_ids_list,
                "scoped_permissions": scoped_permissions_dict,
            }
        except Exception:
            logger.exception(
                "Failed to resolve person in auth_status for email=%s sub=%s",
                email,
                sub,
            )
            # Clear stale session cache so next request retries cleanly.
            request.session.pop("person_db_id", None)
            request.session.pop("needs_onboarding", None)
            request.session.pop("is_admin", None)
            # Degrade gracefully instead of returning 500 — the frontend
            # will see authenticated=False and redirect to login.
            return {
                "authenticated": False,
                "oidc_configured": oidc_configured,
                "error": "person_resolution_failed",
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

    Updates the person's name and functie immediately. Instead of creating
    an org placement directly, a placement *request* is created which must
    be approved by the team manager or an admin.
    """
    # Validate that the org unit exists.
    org_stmt = select(OrganisatieEenheid.id, OrganisatieEenheid.naam).where(
        OrganisatieEenheid.id == body.organisatie_eenheid_id
    )
    org_result = await db.execute(org_stmt)
    org_row = org_result.first()
    if org_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Organisatie-eenheid niet gevonden",
        )

    # Always update naam and functie (allows corrections on re-submit).
    current_user.naam = body.naam
    current_user.functie = body.functie

    # Create a placement request if the user has no active placement and no
    # pending request for this eenheid yet.
    existing_placement = await db.execute(
        select(PersonOrganisatieEenheid.id).where(
            PersonOrganisatieEenheid.person_id == current_user.id,
            PersonOrganisatieEenheid.eind_datum.is_(None),
        )
    )
    if existing_placement.scalar_one_or_none() is None:
        # Check for existing pending request
        existing_request = await db.execute(
            select(OrgPlacementRequest.id).where(
                OrgPlacementRequest.person_id == current_user.id,
                OrgPlacementRequest.organisatie_eenheid_id
                == body.organisatie_eenheid_id,
                OrgPlacementRequest.status == "pending",
            )
        )
        if existing_request.scalar_one_or_none() is None:
            placement_req = OrgPlacementRequest(
                person_id=current_user.id,
                organisatie_eenheid_id=body.organisatie_eenheid_id,
                dienstverband=body.dienstverband,
            )
            db.add(placement_req)
            await db.flush()

            # Notify team manager and admins
            notif_svc = NotificationService(db)
            await notif_svc.notify_placement_request(
                person_naam=body.naam,
                eenheid_id=body.organisatie_eenheid_id,
                eenheid_naam=org_row.naam,
            )

    await db.flush()

    # Invalidate the session cache so /status re-checks from DB.
    request.session.pop("needs_onboarding", None)
    request.session.pop("person_db_id", None)

    # Re-fetch with eager loading so emails/phones are included in response
    repo = PersonRepository(db)
    person = await repo.get(current_user.id)
    return PersonDetailResponse.model_validate(person)


# ---------------------------------------------------------------------------
# POST /request-access -- submit an access request (public, rate-limited)
# ---------------------------------------------------------------------------

# Stricter rate limiter for access requests.
_access_request_rate_limiter = InMemoryRateLimiter(window=300, max_requests=5)


@router.post("/request-access", response_model=AccessRequestStatusResponse)
async def request_access(
    request: Request,
    body: AccessRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> AccessRequestStatusResponse:
    """Submit an access request. Public endpoint (no auth required)."""
    _access_request_rate_limiter.check(request)

    email = normalize_email(body.email)

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
    email = normalize_email(email)

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
