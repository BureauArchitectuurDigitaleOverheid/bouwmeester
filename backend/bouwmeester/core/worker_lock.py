"""Postgres session-advisory-lock die het background worker-process als
singleton afdwingt.

De backend-container start de worker als losstaand proces naast uvicorn
(zie ``entrypoint.sh``). Bij een deploy/restart kan de oude pod's worker
nog even blijven draaien terwijl de nieuwe al is opgestart — beide zouden
dan hun eigen Mattermost-websocket openen en dezelfde posts verwerken.
``WorkerLock`` voorkomt dat: een tweede instantie kan de lock niet
verkrijgen en moet wachten tot de eerste stopt (of crasht — Postgres
geeft een session-advisory-lock automatisch vrij zodra de onderliggende
connectie sluit, dus een crash zonder nette shutdown is geen probleem).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Vast, willekeurig gekozen bigint — enige vereiste is dat het geen key
# is die elders in de codebase voor een ander doel wordt gebruikt. Eén
# lock-key is genoeg: er is precies één worker-rol om te bewaken.
WORKER_SINGLETON_LOCK_KEY = 728194055201733611


class WorkerLock:
    """Session-advisory-lock op een vaste key, gebonden aan één connectie.

    ``acquire()`` opent een toegewijde connectie uit ``engine`` en probeert
    de lock non-blocking te nemen (``pg_try_advisory_lock``). Die connectie
    blijft open zolang de lock gehouden wordt — advisory locks in Postgres
    zijn per-connectie, dus teruggeven aan de pool zou de lock direct weer
    vrijgeven.
    """

    def __init__(self, engine: AsyncEngine, *, key: int = WORKER_SINGLETON_LOCK_KEY):
        self._engine = engine
        self._key = key
        self._conn: AsyncConnection | None = None

    async def acquire(self) -> bool:
        """Probeer de lock te verkrijgen. Non-blocking: retourneert direct
        ``False`` als een andere houder 'm al vasthoudt, in plaats van te
        wachten."""
        conn = await self._engine.connect()
        result = await conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key}
        )
        got_lock = bool(result.scalar())
        if got_lock:
            self._conn = conn
            return True
        await conn.close()
        return False

    async def release(self) -> None:
        """Geef de lock vrij en sluit de bijbehorende connectie.

        Veilig aan te roepen ongeacht of ``acquire()`` ooit succesvol was
        (bv. in een ``finally``-block) — zonder gehouden lock is dit een
        no-op."""
        if self._conn is None:
            return
        conn, self._conn = self._conn, None
        try:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": self._key}
            )
        finally:
            await conn.close()
