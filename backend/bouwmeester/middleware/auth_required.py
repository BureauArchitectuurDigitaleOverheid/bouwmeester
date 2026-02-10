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

        # Validate the session token against Keycloak (with caching + refresh).
        session: dict = scope.get("session", {})
        if session.get("access_token") and self.settings:
            from bouwmeester.core.auth import validate_session_token

            if await validate_session_token(session, self.settings):
                await self.app(scope, receive, send)
                return

        # No valid session — return 401.
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
