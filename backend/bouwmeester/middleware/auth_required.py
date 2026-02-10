"""Global authentication middleware.

When OIDC is configured, this middleware rejects unauthenticated requests to
``/api/`` routes with a 401 response — except for public paths like
``/api/auth/*`` and ``/api/health/*``.

When OIDC is *not* configured (local development) the middleware is a no-op.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

# Prefixes that are always accessible without authentication.
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/health/",
)


class AuthRequiredMiddleware:
    """ASGI middleware that enforces authentication on API routes."""

    def __init__(self, app: ASGIApp, oidc_configured: bool = False) -> None:
        self.app = app
        self.oidc_configured = oidc_configured

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

        # Check if the session has an access token.
        session: dict = scope.get("session", {})
        if session.get("access_token"):
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
