"""Auth routes -- OIDC login / callback / logout / me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from bouwmeester.core.auth import CurrentUser, get_oauth
from bouwmeester.core.config import Settings, get_settings
from bouwmeester.schema.person import PersonResponse

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
) -> dict:
    """Handle the OIDC callback.

    Exchanges the authorization code for tokens and returns them to the
    caller.  In a real application you would set an HTTP-only cookie or
    create a session; here we return the tokens directly so the SPA can
    store them.
    """
    oauth = get_oauth(settings)
    if oauth is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC is not configured",
        )

    token = await oauth.keycloak.authorize_access_token(request)

    return {
        "access_token": token.get("access_token"),
        "token_type": "bearer",
        "expires_in": token.get("expires_in"),
        "refresh_token": token.get("refresh_token"),
        "id_token": token.get("id_token"),
    }


# ---------------------------------------------------------------------------
# GET /logout -- clear session and redirect to Keycloak logout
# ---------------------------------------------------------------------------


@router.get("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Clear local session state and redirect to the OIDC end-session endpoint."""
    if not settings.OIDC_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OIDC is not configured",
        )

    # Build the OIDC end-session URL.
    end_session_url = (
        f"{settings.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/logout"
    )

    # The post_logout_redirect_uri sends the user back to the app root after
    # Keycloak has ended the session.
    base_url = str(request.base_url).rstrip("/")
    redirect_url = (
        f"{end_session_url}"
        f"?post_logout_redirect_uri={base_url}"
        f"&client_id={settings.OIDC_CLIENT_ID}"
    )

    return RedirectResponse(url=redirect_url)


# ---------------------------------------------------------------------------
# GET /me -- return the currently authenticated user
# ---------------------------------------------------------------------------


@router.get("/me", response_model=PersonResponse)
async def me(current_user: CurrentUser) -> PersonResponse:
    """Return information about the currently authenticated user."""
    return PersonResponse.model_validate(current_user)
