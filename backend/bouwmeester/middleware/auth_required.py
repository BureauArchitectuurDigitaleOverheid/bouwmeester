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
import logging
import time
from collections import defaultdict

import httpx
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import ASGIApp, Receive, Scope, Send

from bouwmeester.core.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter for failed API key attempts.
# Tracks per-IP failure counts within a sliding window.  Not persistent
# across process restarts — intentionally lightweight.
# ---------------------------------------------------------------------------
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_FAILURES = 10  # max failures per window before we slow-log
_api_key_failures: dict[str, list[float]] = defaultdict(list)

# Prefixes that are always accessible without authentication.
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/health/",
    "/api/skill.md",
    "/api/openapi.json",
    "/api/docs",
    "/api/redoc",
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

    async def _validate_api_key(self, token: str, scope: Scope) -> bool:
        """Validate a ``bm_``-prefixed API key against the database.

        We hash the plaintext key and use the hash as a DB lookup key.
        This avoids fetching all hashes for comparison and is safe because
        SHA-256 on high-entropy keys (128-bit) is collision-resistant.
        The constant-time ``verify_api_key`` in ``core/api_key`` is used
        by tests to verify hash correctness, not here.

        On success, stores the matched person's UUID in
        ``scope["_api_key_person_id"]`` so downstream dependencies can
        load the Person by PK instead of re-hashing the key.
        """
        from bouwmeester.core.api_key import hash_api_key
        from bouwmeester.core.database import async_session
        from bouwmeester.models.person import Person

        key_hash = hash_api_key(token)
        try:
            from sqlalchemy import select

            async with async_session() as session:
                stmt = select(Person.id).where(
                    Person.api_key_hash == key_hash,
                    Person.is_active == True,  # noqa: E712
                    Person.is_agent == True,  # noqa: E712
                )
                result = await session.execute(stmt)
                person_id = result.scalar_one_or_none()
                if person_id is not None:
                    scope["_api_key_person_id"] = person_id
                    return True
                return False
        except (SQLAlchemyError, OSError):
            logger.exception("API key validation failed")
            return False

    async def _validate_bearer(self, token: str) -> bool:
        """Validate a Bearer token using the shared auth helpers.

        Tries local JWT validation first (no network call), then falls back
        to the OIDC userinfo endpoint with HTTPS enforcement.
        """
        if not self.settings:
            return False

        from bouwmeester.core.auth import (
            get_http_client,
            get_jwks,
            get_oidc_metadata,
            require_https,
            validate_jwt_locally,
        )

        # 1. Try local JWT validation (fast, no network).
        jwks = await get_jwks(self.settings)
        if jwks:
            claims = validate_jwt_locally(token, jwks, self.settings)
            if claims:
                return True

        # 2. Fall back to userinfo endpoint.
        metadata = await get_oidc_metadata(self.settings)
        if not metadata:
            return False
        userinfo_url = metadata.get("userinfo_endpoint")
        if not userinfo_url:
            return False
        if not require_https(userinfo_url, "Userinfo endpoint"):
            return False

        client = get_http_client()
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

        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # Allow public endpoints through.  Still resolve API-key identity
        # (without enforcing) so /api/auth/me works for agents.
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            bearer_token = _get_bearer_token(scope)
            if bearer_token and bearer_token.startswith("bm_"):
                await self._validate_api_key(bearer_token, scope)
            await self.app(scope, receive, send)
            return

        # 1. Check for bm_ API key (works regardless of OIDC config).
        #    Note: API key auth intentionally bypasses the email whitelist
        #    (step 3 below) — agents are system accounts without emails.
        #    Access control for agents uses Person.is_active instead.
        bearer_token = _get_bearer_token(scope)
        if bearer_token and bearer_token.startswith("bm_"):
            if await self._validate_api_key(bearer_token, scope):
                scope["_auth_validated"] = True
                await self.app(scope, receive, send)
                return
            # Invalid API key → reject immediately (don't fall through to
            # dev-mode passthrough or OIDC — a bm_ token is always ours).
            client = scope.get("client")
            client_host = client[0] if client else "unknown"

            # Track failures per IP for rate-limit awareness.
            now = time.monotonic()
            failures = _api_key_failures[client_host]
            # Prune old entries outside the window.
            failures[:] = [t for t in failures if now - t < _RATE_LIMIT_WINDOW]
            failures.append(now)
            if len(failures) >= _RATE_LIMIT_MAX_FAILURES:
                logger.warning(
                    "Excessive invalid API key attempts (%d in %ds) from %s",
                    len(failures),
                    _RATE_LIMIT_WINDOW,
                    client_host,
                )
            else:
                logger.warning(
                    "Invalid API key attempt from %s on %s",
                    client_host,
                    path,
                )
            body = json.dumps({"detail": "Invalid API key"}).encode("utf-8")
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
            return

        # If OIDC is not configured, pass through (dev mode).
        if not self.oidc_configured:
            await self.app(scope, receive, send)
            return

        # 2. Check OIDC Bearer token (for API clients).
        if bearer_token and not bearer_token.startswith("bm_"):
            if await self._validate_bearer(bearer_token):
                scope["_auth_validated"] = True
                await self.app(scope, receive, send)
                return

        # 3. Validate the session token against Keycloak (with caching + refresh).
        session: dict = scope.get("session", {})
        if session.get("access_token") and self.settings:
            from bouwmeester.core.auth import validate_session_token

            if await validate_session_token(session, self.settings):
                # Check access whitelist — deny even valid sessions
                # for users not on the whitelist.  This is the primary
                # enforcement point; auth_status() has a parallel check
                # that returns a friendly JSON response for the frontend
                # (since /api/auth/* is a public prefix and skips this
                # middleware).
                from bouwmeester.core.whitelist import is_email_allowed

                email = session.get("person_email", "")
                if not is_email_allowed(email):
                    session.clear()
                    body = json.dumps(
                        {"detail": "Access denied — not on whitelist"}
                    ).encode("utf-8")
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
