"""Pydantic schemas for Opdracht and OpdrachtNode."""

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from bouwmeester.schema.externe_organisatie import ExterneOrganisatieResponse


class OpdrachtType(enum.StrEnum):
    opdracht = "opdracht"
    subsidie = "subsidie"


class OpdrachtStatus(enum.StrEnum):
    concept = "concept"
    actief = "actief"
    afgerond = "afgerond"
    verantwoord = "verantwoord"
    geannuleerd = "geannuleerd"


class Kostensoort(enum.StrEnum):
    investering = "investering"
    exploitatie = "exploitatie"
    gemengd = "gemengd"


class OpdrachtNodeRelatieType(enum.StrEnum):
    bekostigt = "bekostigt"
    draagt_bij_aan = "draagt_bij_aan"


# --- OpdrachtNode schemas ---


class OpdrachtNodeCreate(BaseModel):
    node_id: UUID
    relatie_type: OpdrachtNodeRelatieType = OpdrachtNodeRelatieType.bekostigt


class OpdrachtNodeResponse(BaseModel):
    id: UUID
    opdracht_id: UUID
    node_id: UUID
    relatie_type: str
    node_title: str | None = None
    node_type: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="wrap")
    @classmethod
    def _populate_node_fields(cls, data, handler):  # type: ignore[no-untyped-def]
        """Populate node_title/node_type from the nested ORM relationship."""
        if hasattr(data, "node"):
            node = data.node
            obj = handler(data)
            if node is not None:
                obj.node_title = getattr(node, "title", None)
                obj.node_type = getattr(node, "node_type", None)
            return obj
        return handler(data)


# --- Opdracht schemas ---


class OpdrachtBase(BaseModel):
    type: OpdrachtType
    titel: str = Field(min_length=1, max_length=500)
    beschrijving: str | None = Field(None, max_length=10000)
    begrotingsjaar: int = Field(ge=2020, le=2035)
    budget: Decimal | None = Field(None, ge=0)
    gerealiseerd: Decimal | None = Field(None, ge=0)
    kostensoort: Kostensoort | None = None
    volgend_jaar_benodigd: Decimal | None = Field(None, ge=0)
    volgend_jaar_aangevraagd: Decimal | None = Field(None, ge=0)
    instrument_id: UUID | None = None
    opdrachtnemer_id: UUID | None = None
    opdrachtgever_id: UUID | None = None
    verantwoordelijke_id: UUID | None = None
    subsidieregeling: str | None = Field(None, max_length=500)
    beschikking_nummer: str | None = Field(None, max_length=100)
    status: OpdrachtStatus = OpdrachtStatus.concept
    referentie: str | None = Field(None, max_length=200)
    startdatum: date | None = None
    einddatum: date | None = None


class OpdrachtCreate(OpdrachtBase):
    node_koppelingen: list[OpdrachtNodeCreate] | None = None


class OpdrachtUpdate(BaseModel):
    type: OpdrachtType | None = None
    titel: str | None = Field(None, min_length=1, max_length=500)
    beschrijving: str | None = Field(None, max_length=10000)
    begrotingsjaar: int | None = Field(None, ge=2020, le=2035)
    budget: Decimal | None = Field(None, ge=0)
    gerealiseerd: Decimal | None = Field(None, ge=0)
    kostensoort: Kostensoort | None = None
    volgend_jaar_benodigd: Decimal | None = Field(None, ge=0)
    volgend_jaar_aangevraagd: Decimal | None = Field(None, ge=0)
    instrument_id: UUID | None = None
    opdrachtnemer_id: UUID | None = None
    opdrachtgever_id: UUID | None = None
    verantwoordelijke_id: UUID | None = None
    subsidieregeling: str | None = Field(None, max_length=500)
    beschikking_nummer: str | None = Field(None, max_length=100)
    status: OpdrachtStatus | None = None
    referentie: str | None = Field(None, max_length=200)
    startdatum: date | None = None
    einddatum: date | None = None
    # FCC sync (for conflict resolution)
    sync_status: str | None = None

    @field_validator("begrotingsjaar")
    @classmethod
    def begrotingsjaar_not_null(cls, v: int | None) -> int | None:
        """Reject explicit null — begrotingsjaar is required at the DB level."""
        if v is None:
            raise ValueError("begrotingsjaar mag niet null zijn")
        return v


class OpdrachtInstrumentSummary(BaseModel):
    id: UUID
    title: str
    node_type: str

    model_config = ConfigDict(from_attributes=True)


class OpdrachtPersonSummary(BaseModel):
    id: UUID
    naam: str

    model_config = ConfigDict(from_attributes=True)


class OpdrachtOrgSummary(BaseModel):
    id: UUID
    naam: str

    model_config = ConfigDict(from_attributes=True)


class OpdrachtResponse(BaseModel):
    id: UUID
    type: str
    titel: str
    beschrijving: str | None = None
    begrotingsjaar: int
    budget: Decimal | None = None
    gerealiseerd: Decimal | None = None
    kostensoort: str | None = None
    volgend_jaar_benodigd: Decimal | None = None
    volgend_jaar_aangevraagd: Decimal | None = None
    instrument_id: UUID | None = None
    instrument: OpdrachtInstrumentSummary | None = None
    opdrachtnemer_id: UUID | None = None
    opdrachtnemer: ExterneOrganisatieResponse | None = None
    opdrachtgever_id: UUID | None = None
    opdrachtgever: OpdrachtOrgSummary | None = None
    verantwoordelijke_id: UUID | None = None
    verantwoordelijke: OpdrachtPersonSummary | None = None
    subsidieregeling: str | None = None
    beschikking_nummer: str | None = None
    status: str
    referentie: str | None = None
    startdatum: date | None = None
    einddatum: date | None = None
    # FCC sync fields
    fcc_id: str | None = None
    sync_status: str | None = None
    sync_direction: str | None = None
    last_synced_at: datetime | None = None
    node_koppelingen: list[OpdrachtNodeResponse] = []
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Opdrachten summary schema ---


class OpdrachtenSummary(BaseModel):
    count: int = 0
    totaal_budget: Decimal = Decimal("0")
    totaal_gerealiseerd: Decimal = Decimal("0")
    uitnutting_percentage: float | None = None


# --- Financieel overzicht schemas ---


class FinancieelJaar(BaseModel):
    begrotingsjaar: int
    budget: Decimal = Decimal("0")
    gerealiseerd: Decimal = Decimal("0")
    volgend_jaar_benodigd: Decimal = Decimal("0")
    volgend_jaar_aangevraagd: Decimal = Decimal("0")
    opdracht_count: int = 0


class FinancieelOverzicht(BaseModel):
    node_id: UUID
    node_title: str
    node_type: str
    totaal_budget: Decimal = Decimal("0")
    totaal_gerealiseerd: Decimal = Decimal("0")
    uitnutting_percentage: float | None = None
    per_jaar: list[FinancieelJaar] = []
