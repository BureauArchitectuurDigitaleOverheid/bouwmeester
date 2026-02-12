"""Pydantic schemas for AccessRequest."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AccessRequestCreate(BaseModel):
    email: EmailStr
    naam: str = Field(max_length=200)


class AccessRequestResponse(BaseModel):
    id: UUID
    email: str
    naam: str
    status: str
    requested_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by_id: UUID | None = None
    deny_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AccessRequestStatusResponse(BaseModel):
    """Public response for checking request status."""

    has_pending: bool
    status: str | None = None
    deny_reason: str | None = None


class AccessRequestReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|deny)$")
    deny_reason: str | None = Field(None, max_length=500)
