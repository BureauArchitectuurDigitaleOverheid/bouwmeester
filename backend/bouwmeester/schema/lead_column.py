"""Pydantic schemas for LeadColumn (per-initiatief funnel-kolommen)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The closed set of nldd-tag color names a LeadColumn.color may hold. Five
# semantic roles plus the Rijkshuisstijl hue set; kept in sync by hand with
# the frontend map in frontend/src/components/leads/stageColors.ts (the
# nldd-tag element's own `color` attribute is the other source of truth).
# Anything outside this set is invalid; the frontend falls back to 'neutral'
# for a value it does not recognise (e.g. from another environment's data).
LEAD_COLUMN_COLORS: frozenset[str] = frozenset(
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

# Default columns inserted for every initiatief; also the fallback set used
# by orphan-leads (initiatief_id IS NULL) and as a frontend loading fallback.
DEFAULT_COLUMNS: list[dict] = [
    {
        "slug": "inbox",
        "name": "Inbox",
        "color": "lintblauw",
        "is_active_stage": False,
        "is_public_visible": False,
    },
    {
        "slug": "verkennen",
        "name": "Verkennen",
        "color": "hemelblauw",
        "is_active_stage": True,
        "is_public_visible": False,
    },
    {
        "slug": "eerste_gesprek",
        "name": "Eerste gesprek",
        "color": "geel",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "interne_check",
        "name": "Interne check",
        "color": "oranje",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "follow_up",
        "name": "Follow-up",
        "color": "paars",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "in_the_pocket",
        "name": "In the pocket",
        "color": "success",
        "is_active_stage": False,
        "is_public_visible": True,
    },
    {
        "slug": "koelkast",
        "name": "Koelkast",
        "color": "neutral",
        "is_active_stage": False,
        "is_public_visible": False,
    },
]

DEFAULT_SLUGS: frozenset[str] = frozenset(c["slug"] for c in DEFAULT_COLUMNS)
DEFAULT_ACTIVE_SLUGS: frozenset[str] = frozenset(
    c["slug"] for c in DEFAULT_COLUMNS if c["is_active_stage"]
)
DEFAULT_PUBLIC_SLUGS: frozenset[str] = frozenset(
    c["slug"] for c in DEFAULT_COLUMNS if c["is_public_visible"]
)


def _validate_column_color(color: str | None) -> str | None:
    if color is not None and color not in LEAD_COLUMN_COLORS:
        allowed = ", ".join(sorted(LEAD_COLUMN_COLORS))
        raise ValueError(f"color must be one of: {allowed}")
    return color


class LeadColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(description="One of LEAD_COLUMN_COLORS.")
    is_active_stage: bool = True
    is_public_visible: bool = False

    _validate_color = field_validator("color")(_validate_column_color)


class LeadColumnUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    color: str | None = Field(None, description="One of LEAD_COLUMN_COLORS.")
    is_active_stage: bool | None = None
    is_public_visible: bool | None = None

    _validate_color = field_validator("color")(_validate_column_color)


class LeadColumnReorder(BaseModel):
    column_ids: list[UUID] = Field(min_length=1)


class LeadColumnResponse(BaseModel):
    id: UUID
    initiatief_id: UUID
    name: str
    slug: str
    sort_order: int
    color: str
    is_active_stage: bool
    is_public_visible: bool
    lead_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
