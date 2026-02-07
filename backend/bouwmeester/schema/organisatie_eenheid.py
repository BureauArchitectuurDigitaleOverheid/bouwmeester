"""Pydantic schemas for OrganisatieEenheid."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bouwmeester.schema.person import PersonResponse


class OrganisatieEenheidCreate(BaseModel):
    naam: str
    type: str
    parent_id: UUID | None = None
    manager_id: UUID | None = None
    beschrijving: str | None = None


class OrganisatieEenheidUpdate(BaseModel):
    naam: str | None = None
    type: str | None = None
    parent_id: UUID | None = None
    manager_id: UUID | None = None
    beschrijving: str | None = None


class OrganisatieEenheidResponse(BaseModel):
    id: UUID
    naam: str
    type: str
    parent_id: UUID | None = None
    manager_id: UUID | None = None
    manager: PersonResponse | None = None
    beschrijving: str | None = None
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
