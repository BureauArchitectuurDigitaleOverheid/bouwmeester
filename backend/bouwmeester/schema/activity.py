"""Pydantic schemas for Activity."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActivityResponse(BaseModel):
    id: UUID
    event_type: str
    actor_id: UUID | None = None
    actor_naam: str | None = None
    node_id: UUID | None = None
    task_id: UUID | None = None
    edge_id: UUID | None = None
    details: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityFeedResponse(BaseModel):
    items: list[ActivityResponse]
    total: int
