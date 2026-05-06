"""Worker-heartbeat helpers.

Background loops in :mod:`bouwmeester.worker` (and the long-lived Mattermost
websocket service) call :func:`tick` to record they are alive. The admin
``/api/admin/workers`` endpoint reads the table to surface status in the UI.

Each loop owns one row, keyed on ``loop_name``. Writes are upserts so the
worker doesn't need a separate "init" step. Heartbeats are best-effort: a
DB failure here must never crash the loop.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.worker_heartbeat import WorkerHeartbeat

logger = logging.getLogger(__name__)


async def tick(
    loop_name: str,
    *,
    status: str = "ok",
    detail: str | None = None,
) -> None:
    """Record a heartbeat for ``loop_name``. Best-effort: errors are logged
    and swallowed so a flaky DB never kills a worker loop."""
    try:
        async with async_session() as session:
            await _upsert(session, loop_name, status=status, detail=detail)
            await session.commit()
    except Exception:
        logger.exception("worker_health.tick failed for %s", loop_name)


async def _upsert(
    session: AsyncSession,
    loop_name: str,
    *,
    status: str,
    detail: str | None,
) -> None:
    now = datetime.now(UTC)
    stmt = insert(WorkerHeartbeat).values(
        loop_name=loop_name,
        status=status,
        detail=detail,
        last_tick_at=now,
        started_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[WorkerHeartbeat.loop_name],
        set_={
            "status": stmt.excluded.status,
            "detail": stmt.excluded.detail,
            "last_tick_at": stmt.excluded.last_tick_at,
        },
    )
    await session.execute(stmt)
