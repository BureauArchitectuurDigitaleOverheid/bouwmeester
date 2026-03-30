"""Pydantic schemas for unified resource permissions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from bouwmeester.schema.person import PersonResponse

# All valid resource role values (union across all resource types)
_VALID_ROLES: set[str] = {
    "eigenaar",
    "betrokken",
    "adviseur",
    "indiener",
    "contributor",
    "viewer",
    "opdrachtgever",
    "contactpersoon",
    "coordinator",
    "lid",
}


def _validate_rol(v: str) -> str:
    if v not in _VALID_ROLES:
        msg = f"Invalid rol '{v}'. Must be one of: {', '.join(sorted(_VALID_ROLES))}"
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
    person_id: UUID
    person: PersonResponse | None = None
    resource_type: str
    resource_id: UUID
    rol: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonResourcePermissionResponse(ResourcePermissionResponse):
    resource_name: str = ""
