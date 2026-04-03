"""Shared helper for creating FCC sync log entries."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.fcc_sync_log import FccSyncLog


def log_fcc_sync(
    session: AsyncSession,
    *,
    opdracht_id: UUID | None = None,
    direction: str,
    action: str,
    details: dict | None = None,
    error_message: str | None = None,
) -> None:
    """Create an FCC sync log entry and add it to the session."""
    log = FccSyncLog(
        opdracht_id=opdracht_id,
        direction=direction,
        action=action,
        details=details,
        error_message=error_message,
    )
    session.add(log)
