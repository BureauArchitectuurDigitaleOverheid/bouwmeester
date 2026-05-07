"""Pydantic schemas for worker heartbeat/health endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkerHeartbeatResponse(BaseModel):
    """Status van één worker-loop, zoals getoond in Beheer > Systeem."""

    model_config = ConfigDict(from_attributes=True)

    loop_name: str
    status: str
    detail: str | None
    last_tick_at: datetime | None
    started_at: datetime | None
    seconds_since_last_tick: float | None
    health: str  # "healthy" | "stale" | "down" | "disabled"


class WorkerHealthResponse(BaseModel):
    """Aggregate response for ``GET /api/admin/workers``."""

    workers: list[WorkerHeartbeatResponse]
    server_now: datetime


class MattermostChannelOverview(BaseModel):
    """Eén gekoppeld kanaal in Beheer > Systeem."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_id: str
    channel_display_name: str
    channel_name: str
    scope_type: str  # "lead" | "initiatief"
    scope_id: UUID
    scope_label: str | None
    auto_note_enabled: bool
    suggest_leads_enabled: bool
    last_seen_post_at: datetime | None
    disabled_at: datetime | None
    created_at: datetime
