"""Global authentication middleware.

When OIDC is configured, this middleware rejects unauthenticated requests to
``/api/`` routes with a 401 response — except for public paths like
``/api/auth/*`` and ``/api/health/*``.

When OIDC is *not* configured (local development) the middleware is a no-op.

Token validation is performed periodically (every 5 minutes) against the
Keycloak userinfo endpoint.  If the access token has expired, the middleware
attempts a refresh using the stored refresh token before rejecting the request.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from bouwmeester.core.config import Settings

# Prefixes that are always accessible without authentication.
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/health/",
)


def _get_bearer_token(scope: Scope) -> str | None:
    """Extract Bearer token from the Authorization header, if present."""
    headers = dict(scope.get("headers", []))
    auth_value = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
    if auth_value.startswith("Bearer "):
        token = auth_value.removeprefix("Bearer ").strip()
        return token or None
    return None


class AuthRequiredMiddleware:
    """ASGI middleware that enforces authentication on API routes."""

    def __init__(
        self,
        app: ASGIApp,
        oidc_configured: bool = False,
        settings: Settings | None = None,
    ) -> None:
        self.app = app
        self.oidc_configured = oidc_configured
        self.settings = settings

    async def _validate_bearer(self, token: str) -> bool:
        """Validate a Bearer token against the OIDC userinfo endpoint."""
        if not self.settings:
            return False
        from bouwmeester.core.auth import _get_http_client, get_oidc_metadata

        metadata = await get_oidc_metadata(self.settings)
        if not metadata:
            return False
        userinfo_url = metadata.get("userinfo_endpoint")
        if not userinfo_url:
            return False
        import httpx

        client = _get_http_client()
        try:
            resp = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Only enforce on /api/ routes (not static files, etc.)
        path: str = scope.get("path", "")

        if not self.oidc_configured or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # Allow public endpoints through.
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return

        # 1. Check Bearer token (for API clients).
        bearer_token = _get_bearer_token(scope)
        if bearer_token:
            if await self._validate_bearer(bearer_token):
                await self.app(scope, receive, send)
                return

        # 2. Validate the session token against Keycloak (with caching + refresh).
        session: dict = scope.get("session", {})
        if session.get("access_token") and self.settings:
            from bouwmeester.core.auth import validate_session_token

            if await validate_session_token(session, self.settings):
                await self.app(scope, receive, send)
                return

        # No valid session or Bearer token — return 401.
        body = json.dumps({"detail": "Authentication required"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
