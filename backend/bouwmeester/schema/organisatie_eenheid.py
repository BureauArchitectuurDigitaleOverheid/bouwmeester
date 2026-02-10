"""Pydantic schemas for OrganisatieEenheid."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from bouwmeester.schema.person import PersonResponse

# --- Temporal record schemas ---


class OrgNaamRecord(BaseModel):
    id: UUID
    naam: str
    geldig_van: date
    geldig_tot: date | None = None

    model_config = ConfigDict(from_attributes=True)


class OrgParentRecord(BaseModel):
    id: UUID
    parent_id: UUID
    geldig_van: date
    geldig_tot: date | None = None

    model_config = ConfigDict(from_attributes=True)


class OrgManagerRecord(BaseModel):
    id: UUID
    manager_id: UUID | None = None
    manager: PersonResponse | None = None
    geldig_van: date
    geldig_tot: date | None = None

    model_config = ConfigDict(from_attributes=True)


# --- CRUD schemas ---


class OrganisatieEenheidCreate(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=100)
    parent_id: UUID | None = None
    manager_id: UUID | None = None
    beschrijving: str | None = Field(None, max_length=5000)
    geldig_van: date | None = None  # defaults to today in repository


class OrganisatieEenheidUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=200)
    type: str | None = Field(None, min_length=1, max_length=100)
    parent_id: UUID | None = None
    manager_id: UUID | None = None
    beschrijving: str | None = Field(None, max_length=5000)
    geldig_tot: date | None = None  # to dissolve the unit
    wijzig_datum: date | None = None  # effective date of the change


class OrganisatieEenheidResponse(BaseModel):
    id: UUID
    naam: str
    type: str
    parent_id: UUID | None = None
    manager_id: UUID | None = None
    manager: PersonResponse | None = None
    beschrijving: str | None = None
    geldig_van: date | None = None
    geldig_tot: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganisatieEenheidTreeNode(OrganisatieEenheidResponse):
    children: list[OrganisatieEenheidTreeNode] = []
    personen_count: int = 0


class OrganisatieEenheidPersonenGroup(BaseModel):
    eenheid: OrganisatieEenheidResponse
    personen: list[PersonResponse]
    children: list[OrganisatieEenheidPersonenGroup] = []

    model_config = ConfigDict(from_attributes=True)
