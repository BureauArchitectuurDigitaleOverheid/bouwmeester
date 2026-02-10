"""Server-side session store.

Stores session data keyed by session ID.  Each session has a TTL after which it
is considered expired.  A background cleanup coroutine removes stale entries
periodically.

The browser cookie only contains a signed session ID (via ``itsdangerous``);
all actual data lives server-side in the database.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary secret string."""
    raw = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(raw)


class SessionStore(ABC):
    """Abstract base class for session stores."""

    @abstractmethod
    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Return session data for *session_id*, or ``None`` if missing/expired."""

    @abstractmethod
    async def set(self, session_id: str, data: dict[str, Any]) -> None:
        """Persist *data* under *session_id*, resetting the TTL."""

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Remove the session identified by *session_id*."""

    @abstractmethod
    async def cleanup(self) -> int:
        """Remove expired sessions.  Returns the number of sessions removed."""


class DatabaseSessionStore(SessionStore):
    """Database-backed session store.

    Sessions survive backend restarts and work across replicas.
    Uses the ``http_sessions`` table.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ttl_seconds: int = 3600,
        encryption_key: str = "",
    ) -> None:
        self._session_factory = session_factory
        self._ttl = ttl_seconds
        self._fernet: Fernet | None = None
        if encryption_key:
            self._fernet = Fernet(_derive_fernet_key(encryption_key))

    async def get(self, session_id: str) -> dict[str, Any] | None:
        from bouwmeester.models.http_session import HttpSession

        async with self._session_factory() as db:
            stmt = select(HttpSession).where(HttpSession.session_id == session_id)
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            if row.expires_at < datetime.now(UTC):
                await db.delete(row)
                await db.commit()
                return None
            raw = row.data
            if self._fernet:
                try:
                    raw = self._fernet.decrypt(raw.encode()).decode()
                except InvalidToken:
                    logger.warning("Failed to decrypt session %s", session_id)
                    await db.delete(row)
                    await db.commit()
                    return None
            return json.loads(raw)

    async def set(self, session_id: str, data: dict[str, Any]) -> None:
        from bouwmeester.models.http_session import HttpSession

        async with self._session_factory() as db:
            expires_at = datetime.now(UTC) + timedelta(seconds=self._ttl)
            data_json = json.dumps(data)
            if self._fernet:
                data_json = self._fernet.encrypt(data_json.encode()).decode()
            stmt = (
                pg_insert(HttpSession)
                .values(
                    session_id=session_id,
                    data=data_json,
                    expires_at=expires_at,
                )
                .on_conflict_do_update(
                    index_elements=["session_id"],
                    set_={"data": data_json, "expires_at": expires_at},
                )
            )
            await db.execute(stmt)
            await db.commit()

    async def delete(self, session_id: str) -> None:
        from bouwmeester.models.http_session import HttpSession

        async with self._session_factory() as db:
            stmt = delete(HttpSession).where(HttpSession.session_id == session_id)
            await db.execute(stmt)
            await db.commit()

    async def cleanup(self) -> int:
        from bouwmeester.models.http_session import HttpSession

        async with self._session_factory() as db:
            now = datetime.now(UTC)
            stmt = (
                delete(HttpSession)
                .where(HttpSession.expires_at < now)
                .returning(text("1"))
            )
            result = await db.execute(stmt)
            count = len(result.all())
            await db.commit()
        if count:
            logger.info("Cleaned up %d expired sessions", count)
        return count


async def run_cleanup_loop(
    store: SessionStore,
    interval_seconds: int = 300,
) -> None:
    """Background task that periodically cleans up expired sessions."""
    consecutive_failures = 0
    max_backoff = 3600  # Cap at 1 hour
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await store.cleanup()
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            backoff = min(interval_seconds * (2**consecutive_failures), max_backoff)
            logger.exception(
                "Session cleanup failed (%d consecutive), next attempt in %ds",
                consecutive_failures,
                backoff,
            )
            await asyncio.sleep(backoff)
