"""Pydantic schemas for LeadColumn (per-initiatief funnel-kolommen)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Default columns inserted for every initiatief; also the fallback set used
# by orphan-leads (initiatief_id IS NULL) and as a frontend loading fallback.
DEFAULT_COLUMNS: list[dict] = [
    {
        "slug": "inbox",
        "name": "Inbox",
        "color": "bg-indigo-100 text-indigo-800",
        "is_active_stage": False,
        "is_public_visible": False,
    },
    {
        "slug": "verkennen",
        "name": "Verkennen",
        "color": "bg-blue-100 text-blue-800",
        "is_active_stage": True,
        "is_public_visible": False,
    },
    {
        "slug": "eerste_gesprek",
        "name": "Eerste gesprek",
        "color": "bg-yellow-100 text-yellow-800",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "interne_check",
        "name": "Interne check",
        "color": "bg-orange-100 text-orange-800",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "follow_up",
        "name": "Follow-up",
        "color": "bg-purple-100 text-purple-800",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "in_the_pocket",
        "name": "In the pocket",
        "color": "bg-green-100 text-green-800",
        "is_active_stage": False,
        "is_public_visible": True,
    },
    {
        "slug": "koelkast",
        "name": "Koelkast",
        "color": "bg-gray-100 text-gray-800",
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


class LeadColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(min_length=1, max_length=120)
    is_active_stage: bool = True
    is_public_visible: bool = False


class LeadColumnUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    color: str | None = Field(None, min_length=1, max_length=120)
    is_active_stage: bool | None = None
    is_public_visible: bool | None = None


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
