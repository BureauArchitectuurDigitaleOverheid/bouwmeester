"""Pydantic schemas for LeadUpdatePost."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LeadUpdatePostCreate(BaseModel):
    titel: str = Field(min_length=1, max_length=300)
    body_internal: str | None = Field(None, max_length=50000)
    body_public: str | None = Field(None, max_length=5000)
    mail_subject: str | None = Field(None, max_length=300)
    mail_to: list[EmailStr] | None = None
    mail_cc: list[EmailStr] | None = None
    source_raw_text: str | None = Field(None, max_length=50000)
    publish: bool = False


class LeadUpdatePostEdit(BaseModel):
    titel: str | None = Field(None, min_length=1, max_length=300)
    body_internal: str | None = Field(None, max_length=50000)
    body_public: str | None = Field(None, max_length=5000)
    mail_subject: str | None = Field(None, max_length=300)
    mail_to: list[EmailStr] | None = None
    mail_cc: list[EmailStr] | None = None


class LeadUpdatePostResponse(BaseModel):
    id: UUID
    lead_id: UUID
    titel: str
    body_internal: str | None = None
    body_public: str | None = None
    mail_subject: str | None = None
    mail_to: list[str] | None = None
    mail_cc: list[str] | None = None
    published_at: datetime | None = None
    published_by_id: UUID | None = None
    published_by_naam: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadUpdatePostPublicResponse(BaseModel):
    """Subset safe to expose under a casus on /c/:slug."""

    titel: str
    body_public: str | None = None
    published_at: datetime
    published_by_naam: str | None = None


class LeadUpdateExtractResult(BaseModel):
    """LLM-extracted draft for a lead-update; user reviews + edits before save."""

    titel: str | None = None
    body_internal: str | None = None
    body_public: str | None = None
    mail_subject: str | None = None
    suggested_to: list[str] = Field(default_factory=list)
    suggested_cc: list[str] = Field(default_factory=list)
