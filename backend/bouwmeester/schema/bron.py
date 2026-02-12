"""Pydantic schemas for Bron and BronBijlage."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

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


def _check_url_scheme(v: str | None) -> str | None:
    if v is not None and not v.startswith(("http://", "https://")):
        raise ValueError("URL moet beginnen met http:// of https://")
    return v


class BronBase(BaseModel):
    type: BronType = "overig"
    auteur: str | None = None
    publicatie_datum: date | None = None
    url: str | None = None


class BronCreate(BronBase):
    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        return _check_url_scheme(v)


class BronUpdate(BaseModel):
    # type is NOT NULL in DB, so don't accept None here.
    # Omitting type from the request is fine (exclude_unset skips it).
    type: BronType = "overig"
    auteur: str | None = None
    publicatie_datum: date | None = None
    url: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        return _check_url_scheme(v)


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
