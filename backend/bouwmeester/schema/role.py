"""Pydantic schemas for RBAC: roles, permissions, and person role assignments."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RoleResponse(BaseModel):
    id: str
    naam: str
    description: str | None = None
    level: str
    rank: int

    model_config = ConfigDict(from_attributes=True)


class PermissionResponse(BaseModel):
    id: str
    category: str

    model_config = ConfigDict(from_attributes=True)


class RoleWithPermissionsResponse(BaseModel):
    id: str
    naam: str
    description: str | None = None
    level: str
    rank: int
    permissions: list[str]

    model_config = ConfigDict(from_attributes=True)


class PersonRoleCreate(BaseModel):
    person_id: UUID
    role_id: str
    organisatie_eenheid_id: UUID | None = None
    start_datum: date | None = None
    eind_datum: date | None = None


class PersonRoleResponse(BaseModel):
    id: UUID
    person_id: UUID
    person_naam: str | None = None
    role_id: str
    role_naam: str | None = None
    organisatie_eenheid_id: UUID | None = None
    organisatie_eenheid_naam: str | None = None
    granted_by_id: UUID | None = None
    start_datum: date
    eind_datum: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MyPermissionsResponse(BaseModel):
    roles: list[PersonRoleResponse]
    permissions: list[str]
    scoped_permissions: dict[str, list[str]] = {}
