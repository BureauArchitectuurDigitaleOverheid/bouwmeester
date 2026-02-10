"""CSRF protection middleware (double-submit cookie pattern).

Generates a CSRF token per session and sets it as a readable cookie
(``bm_csrf``).  State-changing requests (POST, PUT, PATCH, DELETE) must
include the token in an ``X-CSRF-Token`` header.

Bearer-token authenticated requests (API clients) are exempt because they
are not vulnerable to CSRF — the browser never sends the Authorization
header automatically.
"""

from __future__ import annotations

import json
import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_CSRF_COOKIE_NAME = "bm_csrf"
_CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Paths exempt from CSRF checks (public endpoints).
_CSRF_EXEMPT_PREFIXES = (
    "/api/auth/callback",
    "/api/health/",
)


class CSRFMiddleware:
    """ASGI middleware that enforces CSRF tokens on state-changing requests."""

    def __init__(
        self,
        app: ASGIApp,
        cookie_domain: str = "",
        cookie_secure: bool = False,
    ) -> None:
        self.app = app
        self.cookie_domain = cookie_domain
        self.cookie_secure = cookie_secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")

        # Only enforce on /api/ routes.
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # Exempt public endpoints.
        if any(path.startswith(prefix) for prefix in _CSRF_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Bearer-token requests are exempt (not vulnerable to CSRF).
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        if auth_value.startswith("Bearer "):
            await self.app(scope, receive, send)
            return

        session: dict = scope.get("session", {})

        # Ensure a CSRF token exists in the session.
        csrf_token = session.get("csrf_token")
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            session["csrf_token"] = csrf_token

        # For mutating methods, validate the CSRF header.
        if method not in _SAFE_METHODS:
            header_token = (
                headers.get(_CSRF_HEADER.encode(), b"")
                .decode("utf-8", errors="ignore")
                .strip()
            )
            if not header_token or not secrets.compare_digest(header_token, csrf_token):
                body = json.dumps({"detail": "CSRF token missing or invalid"}).encode(
                    "utf-8"
                )
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return

        # Set the CSRF cookie on every response so the frontend can read it.
        async def send_with_csrf_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                from starlette.datastructures import MutableHeaders

                resp_headers = MutableHeaders(scope=message)
                cookie_parts = [
                    f"{_CSRF_COOKIE_NAME}={csrf_token}",
                    "Path=/",
                    "SameSite=Lax",
                ]
                if self.cookie_domain:
                    cookie_parts.append(f"Domain={self.cookie_domain}")
                if self.cookie_secure:
                    cookie_parts.append("Secure")
                # Intentionally NOT HttpOnly — JS must read this cookie.
                resp_headers.append("set-cookie", "; ".join(cookie_parts))
            await send(message)

        await self.app(scope, receive, send_with_csrf_cookie)
