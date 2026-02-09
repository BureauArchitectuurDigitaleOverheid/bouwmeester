"""Pydantic schemas for Notification."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationType(enum.StrEnum):
    task_assigned = "task_assigned"
    task_overdue = "task_overdue"
    task_completed = "task_completed"
    task_reassigned = "task_reassigned"
    node_updated = "node_updated"
    edge_created = "edge_created"
    coverage_needed = "coverage_needed"
    stakeholder_added = "stakeholder_added"
    stakeholder_role_changed = "stakeholder_role_changed"
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
    parent_id: UUID | None = None


class NotificationCreate(NotificationBase):
    pass


class NotificationResponse(NotificationBase):
    id: UUID
    is_read: bool = False
    created_at: datetime
    sender_name: str | None = None
    reply_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SendMessageRequest(BaseModel):
    person_id: UUID
    sender_id: UUID
    message: str


class ReplyRequest(BaseModel):
    sender_id: UUID
    message: str


class UnreadCountResponse(BaseModel):
    count: int


class DashboardStatsResponse(BaseModel):
    corpus_node_count: int
    open_task_count: int
    overdue_task_count: int
