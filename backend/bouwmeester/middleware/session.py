"""Server-side session middleware (ASGI).

Reads a signed session-ID cookie from the request, loads session data from the
:class:`~bouwmeester.core.session_store.SessionStore`, and exposes it via
``request.session``.  On the way out it persists any changes and
sets/clears the cookie.

The cookie itself only contains a random, signed session ID -- all actual data
lives in the server-side store.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bouwmeester.core.session_store import SessionStore

logger = logging.getLogger(__name__)

COOKIE_NAME = "bm_session"


class ServerSideSessionMiddleware:
    """ASGI middleware that provides server-side sessions."""

    def __init__(
        self,
        app: ASGIApp,
        store: SessionStore,
        secret_key: str,
        cookie_domain: str = "",
        cookie_secure: bool = False,
        cookie_max_age: int = 3600,
    ) -> None:
        self.app = app
        self.store = store
        self.signer = TimestampSigner(secret_key)
        self.cookie_domain = cookie_domain
        self.cookie_secure = cookie_secure
        self.cookie_max_age = cookie_max_age

    def _build_cookie(self, value: str, max_age: int) -> str:
        """Build a Set-Cookie header value for the session cookie."""
        parts = [
            f"{COOKIE_NAME}={value}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={max_age}",
        ]
        if self.cookie_domain:
            parts.append(f"Domain={self.cookie_domain}")
        if self.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)

        # --- Load session from cookie ---
        session_id: str | None = None
        session_data: dict[str, Any] = {}
        cookie_value = connection.cookies.get(COOKIE_NAME)

        if cookie_value:
            try:
                session_id = self.signer.unsign(
                    cookie_value, max_age=self.cookie_max_age
                ).decode("utf-8")
                data = await self.store.get(session_id)
                if data is not None:
                    session_data = data
                else:
                    session_id = None
            except (BadSignature, SignatureExpired):
                session_id = None
            except Exception:
                logger.exception("Failed to load session from store")
                session_id = None

        scope["session"] = session_data
        initial_data = dict(session_data)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                nonlocal session_id
                current_data: dict[str, Any] = scope.get("session", {})

                headers = MutableHeaders(scope=message)

                try:
                    # Handle session ID rotation (e.g. after login).
                    # The handler sets ``_rotate`` to signal that a new session ID
                    # should be issued, preventing session fixation attacks.
                    needs_rotation = current_data.pop("_rotate", False)
                    if needs_rotation and session_id is not None:
                        # Delete the old session from the store.
                        await self.store.delete(session_id)
                        session_id = None

                    if current_data:
                        if session_id is None:
                            session_id = secrets.token_urlsafe(32)
                        if current_data != initial_data or needs_rotation:
                            await self.store.set(session_id, current_data)
                        signed = self.signer.sign(session_id).decode("utf-8")
                        headers.append(
                            "set-cookie",
                            self._build_cookie(signed, self.cookie_max_age),
                        )
                    elif session_id is not None:
                        await self.store.delete(session_id)
                        headers.append("set-cookie", self._build_cookie("", 0))
                except Exception:
                    logger.exception("Failed to persist session")

            await send(message)

        await self.app(scope, receive, send_wrapper)
