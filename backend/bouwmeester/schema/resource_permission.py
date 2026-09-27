"""Pydantic schemas for unified resource permissions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from bouwmeester.core.resource_roles import RESOURCE_ROLES
from bouwmeester.schema.person import PersonResponse


def _validate_rol(v: str) -> str:
    if v not in RESOURCE_ROLES:
        msg = f"Invalid rol '{v}'. Must be one of: {', '.join(sorted(RESOURCE_ROLES))}"
        raise ValueError(msg)
    return v


class ResourcePermissionCreate(BaseModel):
    person_id: UUID
    rol: str

    @field_validator("rol")
    @classmethod
    def check_rol(cls, v: str) -> str:
        return _validate_rol(v)


class ResourcePermissionUpdate(BaseModel):
    rol: str

    @field_validator("rol")
    @classmethod
    def check_rol(cls, v: str) -> str:
        return _validate_rol(v)


class ResourcePermissionResponse(BaseModel):
    id: UUID
    person_id: UUID | None = None
    person: PersonResponse | None = None
    resource_type: str
    resource_id: UUID
    rol: str
    source: str | None = "manual"
    ai_confidence: float | None = None
    ai_reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonResourcePermissionResponse(ResourcePermissionResponse):
    resource_name: str = ""
