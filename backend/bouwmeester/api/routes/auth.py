"""Auth routes -- OIDC login / callback / logout / status / me."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from bouwmeester.core.auth import CurrentUser, get_oauth
from bouwmeester.core.config import Settings, get_settings
from bouwmeester.schema.person import PersonDetailResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# GET /login -- redirect to Keycloak authorization page
# ---------------------------------------------------------------------------


@router.get("/login")
async def login(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the user to the OIDC provider login page."""
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC is not configured",
        )

    redirect_uri = str(request.url_for("callback"))
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
    id_token = request.session.get("id_token")

    # Clear all session data.
    request.session.clear()

    if not settings.OIDC_ISSUER:
        return RedirectResponse(url=settings.FRONTEND_URL, status_code=302)

    # Build the OIDC end-session URL.
    end_session_url = (
        f"{settings.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/logout"
    )

    redirect_url = (
        f"{end_session_url}"
        f"?post_logout_redirect_uri={settings.FRONTEND_URL}"
        f"&client_id={settings.OIDC_CLIENT_ID}"
    )
    if id_token:
        redirect_url += f"&id_token_hint={id_token}"

    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# GET /status -- check auth status (used by frontend on load)
# ---------------------------------------------------------------------------


@router.get("/status")
async def auth_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return authentication status for the current session."""
    oidc_configured = bool(settings.OIDC_ISSUER)
    authenticated = bool(request.session.get("access_token"))

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
