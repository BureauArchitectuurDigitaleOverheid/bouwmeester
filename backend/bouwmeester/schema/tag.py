"""Pydantic schemas for Tag management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    description: str | None = Field(None, max_length=2000)


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    parent_id: UUID | None = None
    description: str | None = Field(None, max_length=2000)


class TagResponse(TagBase):
    # Override fields without length constraints — response schemas must be
    # able to return data that already exists in the database.
    name: str
    description: str | None = None

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
    tag_name: str | None = Field(None, max_length=200)  # For creating tag inline


# Resolve forward refs
TagTreeResponse.model_rebuild()
