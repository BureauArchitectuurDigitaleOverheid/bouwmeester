"""Pydantic schemas for Person."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PersonBase(BaseModel):
    naam: str
    email: str
    afdeling: str | None = None
    functie: str | None = None
    rol: str | None = None
    organisatie_eenheid_id: UUID | None = None


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    naam: str | None = None
    email: str | None = None
    afdeling: str | None = None
    functie: str | None = None
    rol: str | None = None
    organisatie_eenheid_id: UUID | None = None


class PersonResponse(PersonBase):
    id: UUID
    is_active: bool
    created_at: datetime

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
