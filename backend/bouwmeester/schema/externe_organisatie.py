"""Pydantic schemas for ExterneOrganisatie."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExterneOrganisatieType(enum.StrEnum):
    uitvoeringsorganisatie = "uitvoeringsorganisatie"
    zbo = "zbo"
    koepelorganisatie = "koepelorganisatie"
    stichting = "stichting"
    marktpartij = "marktpartij"
    overig = "overig"


class ExterneOrganisatieBase(BaseModel):
    naam: str = Field(min_length=1, max_length=300)
    afkorting: str | None = Field(None, max_length=50)
    type: ExterneOrganisatieType
    kvk_nummer: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=500)
    beschrijving: str | None = Field(None, max_length=5000)


class ExterneOrganisatieCreate(ExterneOrganisatieBase):
    pass


class ExterneOrganisatieUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=300)
    afkorting: str | None = Field(None, max_length=50)
    type: ExterneOrganisatieType | None = None
    kvk_nummer: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=500)
    beschrijving: str | None = Field(None, max_length=5000)


class ExterneOrganisatieResponse(BaseModel):
    id: UUID
    naam: str
    afkorting: str | None = None
    type: str
    kvk_nummer: str | None = None
    website: str | None = None
    beschrijving: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
