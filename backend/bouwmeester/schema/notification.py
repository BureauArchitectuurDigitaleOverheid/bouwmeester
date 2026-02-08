"""Pydantic schemas for Notification."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationType(enum.StrEnum):
    task_assigned = "task_assigned"
    task_overdue = "task_overdue"
    node_updated = "node_updated"
    edge_created = "edge_created"
    coverage_needed = "coverage_needed"
    politieke_input_imported = "politieke_input_imported"
    direct_message = "direct_message"
    agent_prompt = "agent_prompt"
    mention = "mention"


class NotificationBase(BaseModel):
    person_id: UUID
    type: NotificationType
    title: str
    message: str | None = None
    sender_id: UUID | None = None
    related_node_id: UUID | None = None
    related_task_id: UUID | None = None


class NotificationCreate(NotificationBase):
    pass


class NotificationResponse(NotificationBase):
    id: UUID
    is_read: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SendMessageRequest(BaseModel):
    person_id: UUID
    sender_id: UUID
    message: str


class UnreadCountResponse(BaseModel):
    count: int
