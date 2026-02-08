"""Pydantic schemas for Mention."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MentionBase(BaseModel):
    source_type: str
    source_id: UUID
    mention_type: str
    target_id: UUID
    created_by: UUID | None = None


class MentionCreate(MentionBase):
    pass


class MentionResponse(MentionBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MentionSearchResult(BaseModel):
    id: str
    label: str
    type: str
    subtitle: str | None = None


class MentionReference(BaseModel):
    source_type: str
    source_id: UUID
    source_title: str
