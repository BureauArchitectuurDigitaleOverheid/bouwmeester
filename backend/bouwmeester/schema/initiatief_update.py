"""Pydantic schemas for InitiatiefUpdatePost."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InitiatiefUpdatePostCreate(BaseModel):
    titel: str = Field(min_length=1, max_length=300)
    body: str | None = Field(None, max_length=50000)
    publish: bool = False  # if true, set published_at to now()


class InitiatiefUpdatePostEdit(BaseModel):
    titel: str | None = Field(None, min_length=1, max_length=300)
    body: str | None = Field(None, max_length=50000)


class InitiatiefUpdatePostResponse(BaseModel):
    id: UUID
    initiatief_id: UUID
    titel: str
    body: str | None = None
    published_at: datetime | None = None
    published_by_id: UUID | None = None
    published_by_naam: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class InitiatiefUpdatePostPublicResponse(BaseModel):
    """Subset of fields safe to expose on the public /c/:slug page."""

    titel: str
    body: str | None = None
    published_at: datetime
    published_by_naam: str | None = None
