"""Pydantic schemas for Bron and BronBijlage."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

BronType = Literal[
    "rapport",
    "onderzoek",
    "wetgeving",
    "advies",
    "opinie",
    "beleidsnota",
    "evaluatie",
    "overig",
]


class BronBase(BaseModel):
    type: BronType = "overig"
    auteur: str | None = None
    publicatie_datum: date | None = None
    url: str | None = None


class BronCreate(BronBase):
    pass


class BronUpdate(BaseModel):
    type: BronType | None = None
    auteur: str | None = None
    publicatie_datum: date | None = None
    url: str | None = None


class BronResponse(BronBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)


class BronBijlageResponse(BaseModel):
    id: UUID
    bestandsnaam: str
    content_type: str
    bestandsgrootte: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
