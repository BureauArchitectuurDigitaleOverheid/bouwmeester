"""Global authentication middleware.

When OIDC is configured, this middleware rejects unauthenticated requests to
``/api/`` routes with a 401 response -- except for public paths like
``/api/auth/*`` and ``/api/health/*``.

When OIDC is *not* configured (local development) the middleware is a no-op.

Bearer tokens are validated via the shared :func:`~bouwmeester.core.auth`
helpers (local JWT check first, then userinfo endpoint).  Session-based
tokens are validated via :func:`~bouwmeester.core.auth.validate_session_token`
which includes periodic revalidation, refresh, and a grace period.

On success the middleware sets ``scope["_auth_validated"] = True`` so that
downstream FastAPI dependencies can skip redundant validation.
"""

from __future__ import annotations

import json

import httpx
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
        """Validate a Bearer token using the shared auth helpers.

        Tries local JWT validation first (no network call), then falls back
        to the OIDC userinfo endpoint with HTTPS enforcement.
        """
        if not self.settings:
            return False

        from bouwmeester.core.auth import (
            _get_http_client,
            _get_jwks,
            _require_https,
            _validate_jwt_locally,
            get_oidc_metadata,
        )

        # 1. Try local JWT validation (fast, no network).
        jwks = await _get_jwks(self.settings)
        if jwks:
            claims = _validate_jwt_locally(token, jwks, self.settings)
            if claims:
                return True

        # 2. Fall back to userinfo endpoint.
        metadata = await get_oidc_metadata(self.settings)
        if not metadata:
            return False
        userinfo_url = metadata.get("userinfo_endpoint")
        if not userinfo_url:
            return False
        if not _require_https(userinfo_url, "Userinfo endpoint"):
            return False

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

        # Let CORS preflight (OPTIONS) requests through so CORSMiddleware
        # can respond with the appropriate headers.
        if scope.get("method") == "OPTIONS":
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
                scope["_auth_validated"] = True
                await self.app(scope, receive, send)
                return

        # 2. Validate the session token against Keycloak (with caching + refresh).
        session: dict = scope.get("session", {})
        if session.get("access_token") and self.settings:
            from bouwmeester.core.auth import validate_session_token

            if await validate_session_token(session, self.settings):
                scope["_auth_validated"] = True
                await self.app(scope, receive, send)
                return

        # No valid session or Bearer token -- return 401.
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
