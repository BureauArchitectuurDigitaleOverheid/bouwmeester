"""Pydantic schemas for Samenwerkingsverband."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SamenwerkingsverbandBase(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=50)
    beschrijving: str | None = Field(None, max_length=10_000)
    start_datum: date | None = None
    eind_datum: date | None = None


class SamenwerkingsverbandCreate(SamenwerkingsverbandBase):
    pass


class SamenwerkingsverbandUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=200)
    type: str | None = Field(None, min_length=1, max_length=50)
    beschrijving: str | None = Field(None, max_length=10_000)
    start_datum: date | None = None
    eind_datum: date | None = None


class SamenwerkingsverbandResponse(SamenwerkingsverbandBase):
    id: UUID
    created_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    aantal_leden: int = 0

    model_config = ConfigDict(from_attributes=True)


class SamenwerkingsverbandLidCreate(BaseModel):
    person_id: UUID
    rol: str | None = Field(None, max_length=50)
    start_datum: date


class SamenwerkingsverbandLidUpdate(BaseModel):
    rol: str | None = Field(None, max_length=50)
    eind_datum: date | None = None


class SamenwerkingsverbandLidResponse(BaseModel):
    id: UUID
    samenwerkingsverband_id: UUID
    person_id: UUID
    person_naam: str = ""
    person_functie: str | None = None
    person_expertise: str | None = None
    rol: str | None = None
    start_datum: date
    eind_datum: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SamenwerkingsverbandDetailResponse(SamenwerkingsverbandResponse):
    leden: list[SamenwerkingsverbandLidResponse] = []


class PersoonLidmaatschapResponse(BaseModel):
    """Lidmaatschap vanuit het persoon-perspectief: welke verbanden, welke rol."""

    id: UUID
    samenwerkingsverband_id: UUID
    samenwerkingsverband_naam: str
    samenwerkingsverband_type: str
    rol: str | None = None
    start_datum: date
    eind_datum: date | None = None

    model_config = ConfigDict(from_attributes=True)
