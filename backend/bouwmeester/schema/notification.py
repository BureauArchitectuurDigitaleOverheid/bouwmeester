"""Pydantic schemas for Notification."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    access_request = "access_request"


class NotificationBase(BaseModel):
    person_id: UUID
    type: NotificationType
    title: str = Field(max_length=500)
    message: str | None = Field(None, max_length=10000)
    sender_id: UUID | None = None
    related_node_id: UUID | None = None
    related_task_id: UUID | None = None
    parent_id: UUID | None = None
    thread_id: UUID | None = None


class NotificationCreate(NotificationBase):
    pass


class NotificationResponse(NotificationBase):
    id: UUID
    is_read: bool = False
    created_at: datetime
    last_activity_at: datetime | None = None
    last_message: str | None = None
    sender_name: str | None = None
    reply_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SendMessageRequest(BaseModel):
    person_id: UUID
    sender_id: UUID
    message: str = Field(max_length=10000)


class ReplyRequest(BaseModel):
    sender_id: UUID
    message: str = Field(max_length=10000)


class UnreadCountResponse(BaseModel):
    count: int


class DashboardStatsResponse(BaseModel):
    corpus_node_count: int
    open_task_count: int
    overdue_task_count: int
