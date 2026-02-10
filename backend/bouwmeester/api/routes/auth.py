"""Auth routes -- OIDC login / callback / logout / status / me."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from bouwmeester.core.auth import CurrentUser, get_oauth, validate_session_token
from bouwmeester.core.config import Settings, get_settings
from bouwmeester.schema.person import PersonDetailResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter for auth endpoints
# ---------------------------------------------------------------------------

_rate_limit_window = 60  # seconds
_rate_limit_max = 30  # requests per window per IP
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(request: Request) -> None:
    """Raise 429 if the client IP has exceeded the rate limit."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - _rate_limit_window

    # Prune old entries.
    timestamps = _rate_limit_store[client_ip]
    _rate_limit_store[client_ip] = [t for t in timestamps if t > window_start]

    if len(_rate_limit_store[client_ip]) >= _rate_limit_max:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
        )
    _rate_limit_store[client_ip].append(now)


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

    # Store tokens in the server-side session.
    session = request.session
    session["access_token"] = token.get("access_token")
    session["refresh_token"] = token.get("refresh_token")
    session["id_token"] = token.get("id_token")

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

    # Clear all session data.
    request.session.clear()

    if not settings.OIDC_ISSUER:
        return RedirectResponse(url=settings.FRONTEND_URL, status_code=302)

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
# GET /status -- check auth status (used by frontend on load)
# ---------------------------------------------------------------------------


@router.get("/status")
async def auth_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return authentication status for the current session."""
    _check_rate_limit(request)
    oidc_configured = bool(settings.OIDC_ISSUER)
    authenticated = False

    if request.session.get("access_token") and oidc_configured:
        authenticated = await validate_session_token(request.session, settings)

    result: dict = {
        "authenticated": authenticated,
        "oidc_configured": oidc_configured,
    }

    if authenticated:
        result["person"] = {
            "sub": request.session.get("person_sub", ""),
            "email": request.session.get("person_email", ""),
            "name": request.session.get("person_name", ""),
        }

    return result


# ---------------------------------------------------------------------------
# GET /me -- return the currently authenticated user
# ---------------------------------------------------------------------------


@router.get("/me", response_model=PersonDetailResponse)
async def me(current_user: CurrentUser) -> PersonDetailResponse:
    """Return information about the currently authenticated user."""
    return PersonDetailResponse.model_validate(current_user)
