"""Pydantic schemas for Initiatief."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Canonical eenheid-rol type — used in schemas, routes, and repository
InitiatiefEenheidRol = Literal["eigenaar", "contributor", "viewer"]
EENHEID_ROL_RANK: dict[str, int] = {"eigenaar": 3, "contributor": 2, "viewer": 1}


class InitiatiefBase(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    beschrijving: str | None = Field(None, max_length=5000)
    kleur: str | None = Field(None, max_length=20)


class InitiatiefCreate(InitiatiefBase):
    pass


class InitiatiefUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=200)
    beschrijving: str | None = Field(None, max_length=5000)
    kleur: str | None = Field(None, max_length=20)


class InitiatiefMemberCreate(BaseModel):
    person_id: UUID
    rol: str = "contributor"


class InitiatiefEenheidCreate(BaseModel):
    eenheid_id: UUID
    rol: InitiatiefEenheidRol = "contributor"


class InitiatiefEenheidUpdate(BaseModel):
    rol: InitiatiefEenheidRol


class InitiatiefMemberResponse(BaseModel):
    initiatief_id: UUID
    person_id: UUID
    person_naam: str = ""
    rol: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InitiatiefEenheidResponse(BaseModel):
    initiatief_id: UUID
    eenheid_id: UUID
    eenheid_naam: str = ""
    rol: str = "contributor"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InitiatiefResponse(BaseModel):
    id: UUID
    naam: str
    beschrijving: str | None = None
    kleur: str | None = None
    created_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class InitiatiefDetailResponse(InitiatiefResponse):
    members: list[InitiatiefMemberResponse] = Field(default_factory=list)
    eenheden: list[InitiatiefEenheidResponse] = Field(default_factory=list)
    access_level: str | None = None
