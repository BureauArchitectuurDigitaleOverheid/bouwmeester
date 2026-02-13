"""Pydantic schemas for admin-configurable app settings."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AppConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    value: str  # Masked if is_secret
    description: str | None
    is_secret: bool
    updated_by: str | None
    updated_at: datetime
    created_at: datetime


class AppConfigUpdate(BaseModel):
    value: str
