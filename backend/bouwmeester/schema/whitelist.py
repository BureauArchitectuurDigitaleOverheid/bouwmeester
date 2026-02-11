"""Pydantic schemas for whitelist email management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class WhitelistEmailCreate(BaseModel):
    email: EmailStr = Field(max_length=254)


class WhitelistEmailResponse(BaseModel):
    id: UUID
    email: str
    added_by: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserResponse(BaseModel):
    id: UUID
    naam: str
    email: str | None = None
    functie: str | None = None
    is_admin: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AdminToggleRequest(BaseModel):
    is_admin: bool
