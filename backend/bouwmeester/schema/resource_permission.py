"""Pydantic schemas for unified resource permissions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bouwmeester.schema.person import PersonResponse


class ResourcePermissionCreate(BaseModel):
    person_id: UUID
    rol: str


class ResourcePermissionUpdate(BaseModel):
    rol: str


class ResourcePermissionResponse(BaseModel):
    id: UUID
    person_id: UUID
    person: PersonResponse | None = None
    resource_type: str
    resource_id: UUID
    rol: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
