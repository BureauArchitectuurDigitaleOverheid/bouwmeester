"""Pydantic schemas for Initiatief."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Canonical eenheid-rol type — used in schemas, routes, and repository
InitiatiefEenheidRol = Literal["eigenaar", "contributor", "viewer"]

# The closed set of nldd-tag color names an Initiatief.kleur may hold, the same
# set LeadColumn.color uses (schema.lead_column.LEAD_COLUMN_COLORS): five
# semantic roles plus the Rijkshuisstijl hues. The frontend passes this straight
# to nldd-tag's `color` and nldd-icon's `color`, which ignore anything outside
# their own set, so a hex or a CSS class here renders as no color at all.
# Mirrored by hand in frontend/src/types/index.ts (INITIATIEF_COLORS).
INITIATIEF_COLORS: frozenset[str] = frozenset(
    {
        # Semantic roles
        "neutral",
        "accent",
        "success",
        "warning",
        "critical",
        # Rijkshuisstijl
        "lintblauw",
        "donkerblauw",
        "hemelblauw",
        "lichtblauw",
        "paars",
        "violet",
        "robijnrood",
        "roze",
        "rood",
        "oranje",
        "donkergeel",
        "geel",
        "donkerbruin",
        "bruin",
        "donkergroen",
        "groen",
        "mosgroen",
        "mintgroen",
    }
)


def _validate_kleur(kleur: str | None) -> str | None:
    if kleur is not None and kleur not in INITIATIEF_COLORS:
        allowed = ", ".join(sorted(INITIATIEF_COLORS))
        raise ValueError(f"kleur must be one of: {allowed}")
    return kleur


class InitiatiefBase(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    beschrijving: str | None = Field(None, max_length=5000)
    kleur: str | None = Field(
        None, max_length=20, description="One of INITIATIEF_COLORS."
    )

    _validate_kleur = field_validator("kleur")(_validate_kleur)


class InitiatiefCreate(InitiatiefBase):
    pass


class InitiatiefUpdate(BaseModel):
    naam: str | None = Field(None, min_length=1, max_length=200)
    beschrijving: str | None = Field(None, max_length=5000)
    kleur: str | None = Field(
        None, max_length=20, description="One of INITIATIEF_COLORS."
    )

    _validate_kleur = field_validator("kleur")(_validate_kleur)


class InitiatiefSettingsUpdate(BaseModel):
    """Settings only mutable by an eigenaar."""

    slug: str | None = Field(None, min_length=1, max_length=80)
    funnel_enabled: bool | None = None
    public_page_enabled: bool | None = None
    score_strategisch_label: str | None = Field(None, max_length=120)
    score_politiek_label: str | None = Field(None, max_length=120)
    score_positie_label: str | None = Field(None, max_length=120)


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


class InitiatiefEenheidWithNameResponse(BaseModel):
    initiatief_id: UUID
    initiatief_naam: str = ""
    eenheid_id: UUID
    rol: str = "contributor"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InitiatiefResponse(BaseModel):
    id: UUID
    naam: str
    slug: str | None = None
    beschrijving: str | None = None
    kleur: str | None = None
    funnel_enabled: bool = False
    public_page_enabled: bool = False
    score_strategisch_label: str | None = None
    score_politiek_label: str | None = None
    score_positie_label: str | None = None
    created_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class InitiatiefListItemResponse(InitiatiefResponse):
    """An initiatief as the overview shows it: the record plus what is in it.

    The counts are what a card needs to say whether an initiatief is alive
    without opening it. `active_lead_count` counts leads whose stage sits in
    a column marked as an active stage, so the parked ones (koelkast, in the
    pocket) do not make a quiet initiatief look busy.
    """

    lead_count: int = 0
    active_lead_count: int = 0
    member_count: int = 0
    last_published_at: datetime | None = None


class InitiatiefDetailResponse(InitiatiefResponse):
    members: list[InitiatiefMemberResponse] = Field(default_factory=list)
    eenheden: list[InitiatiefEenheidResponse] = Field(default_factory=list)
    access_level: str | None = None
