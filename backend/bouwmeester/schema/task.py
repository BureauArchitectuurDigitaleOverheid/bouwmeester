"""Pydantic schemas for Task."""

import enum
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(enum.StrEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class TaskPriority(enum.StrEnum):
    laag = "laag"
    normaal = "normaal"
    hoog = "hoog"
    kritiek = "kritiek"


class TaskBase(BaseModel):
    title: str
    description: str | None = None
    node_id: UUID
    assignee_id: UUID | None = None
    status: TaskStatus = TaskStatus.open
    priority: TaskPriority = TaskPriority.normaal
    deadline: date | None = Field(None, alias="due_date")

    model_config = ConfigDict(populate_by_name=True)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    node_id: UUID | None = None
    assignee_id: UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    deadline: date | None = Field(None, alias="due_date")

    model_config = ConfigDict(populate_by_name=True)


class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    node_id: UUID
    assignee_id: UUID | None = None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None = Field(None, validation_alias="deadline")
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
