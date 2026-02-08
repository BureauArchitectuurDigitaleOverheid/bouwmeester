"""Pydantic schemas for Tag management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TagBase(BaseModel):
    name: str
    parent_id: UUID | None = None
    description: str | None = None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None
    description: str | None = None


class TagResponse(TagBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TagTreeResponse(TagResponse):
    children: list["TagTreeResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class NodeTagResponse(BaseModel):
    id: UUID
    tag: TagResponse
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NodeTagCreate(BaseModel):
    tag_id: UUID | None = None
    tag_name: str | None = None  # For creating tag inline


# Resolve forward refs
TagTreeResponse.model_rebuild()
