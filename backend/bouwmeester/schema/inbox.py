"""Pydantic schemas for inbox."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InboxItem(BaseModel):
    type: str  # overdue_task | new_assignment | node_change | coverage_alert
    title: str
    description: str
    related_node_id: UUID | None = None
    related_task_id: UUID | None = None
    created_at: datetime


class InboxResponse(BaseModel):
    items: list[InboxItem]
    total: int
