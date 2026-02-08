"""Pydantic schemas for Person."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PersonBase(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    email: str | None = Field(None, max_length=254)
    functie: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    is_agent: bool = False


class PersonCreate(PersonBase):
    api_key: str | None = None


class PersonUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=200)
    email: str | None = Field(None, max_length=254)
    functie: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    is_agent: bool | None = None
    api_key: str | None = None


class PersonResponse(PersonBase):
    """Response schema for person lists — api_key excluded for security."""

    id: UUID
    is_active: bool
    is_agent: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonDetailResponse(PersonResponse):
    """Full response including api_key — only for get/create/update."""

    api_key: str | None = None


class NodeStakeholderCreate(BaseModel):
    person_id: UUID
    rol: str


class NodeStakeholderUpdate(BaseModel):
    rol: str


class NodeStakeholderResponse(BaseModel):
    id: UUID
    person: PersonResponse
    rol: str

    model_config = ConfigDict(from_attributes=True)


class PersonTaskSummary(BaseModel):
    id: UUID
    title: str
    status: str
    priority: str
    due_date: date | None = Field(None, validation_alias="deadline")

    model_config = ConfigDict(from_attributes=True)


class PersonStakeholderNode(BaseModel):
    node_id: UUID
    node_title: str
    node_type: str
    stakeholder_rol: str


class PersonSummaryResponse(BaseModel):
    open_task_count: int
    done_task_count: int
    open_tasks: list[PersonTaskSummary]
    stakeholder_nodes: list[PersonStakeholderNode]


Dienstverband = Literal["in_dienst", "ingehuurd", "extern"]


class PersonOrganisatieCreate(BaseModel):
    organisatie_eenheid_id: UUID
    dienstverband: Dienstverband = "in_dienst"
    start_datum: date


class PersonOrganisatieUpdate(BaseModel):
    dienstverband: Dienstverband | None = None
    eind_datum: date | None = None


class PersonOrganisatieResponse(BaseModel):
    id: UUID
    person_id: UUID
    organisatie_eenheid_id: UUID
    organisatie_eenheid_naam: str
    dienstverband: str
    start_datum: date
    eind_datum: date | None = None
