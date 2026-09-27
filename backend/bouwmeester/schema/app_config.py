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
    # Whether the caller may change this entry; computed per request by the
    # same rule the PATCH route enforces.
    editable: bool = True


class AppConfigUpdate(BaseModel):
    value: str
