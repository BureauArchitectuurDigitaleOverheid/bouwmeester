"""Pydantic schemas for Lead funnel."""

import enum
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LeadStage(enum.StrEnum):
    verkennen = "verkennen"
    eerste_gesprek = "eerste_gesprek"
    interne_check = "interne_check"
    follow_up = "follow_up"
    in_the_pocket = "in_the_pocket"
    koelkast = "koelkast"


class LeadActivityType(enum.StrEnum):
    note = "note"
    stage_change = "stage_change"
    meeting = "meeting"
    call = "call"
    email = "email"


# ---------------------------------------------------------------------------
# Lead base / create / update
# ---------------------------------------------------------------------------


class LeadBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(None, max_length=10000)
    organization: str | None = Field(None, max_length=500)
    externe_organisatie_id: UUID | None = None
    stage: LeadStage = LeadStage.verkennen
    assignee_id: UUID | None = None
    next_action: str | None = Field(None, max_length=5000)
    next_action_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    raw_intake_text: str | None = Field(None, max_length=50000)
    organisatie_eenheid_id: UUID


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = Field(None, max_length=10000)
    organization: str | None = Field(None, max_length=500)
    externe_organisatie_id: UUID | None = None
    stage: LeadStage | None = None
    assignee_id: UUID | None = None
    next_action: str | None = Field(None, max_length=5000)
    next_action_date: date | None = None
    tags: list[str] | None = None
    raw_intake_text: str | None = Field(None, max_length=50000)
    organisatie_eenheid_id: UUID | None = None

    model_config = ConfigDict(populate_by_name=True)


class LeadMove(BaseModel):
    stage: LeadStage


class LeadReorder(BaseModel):
    lead_ids: list[UUID]
    stage: LeadStage


# ---------------------------------------------------------------------------
# Summary / nested response schemas
# ---------------------------------------------------------------------------


class LeadAssigneeSummary(BaseModel):
    id: UUID
    naam: str

    model_config = ConfigDict(from_attributes=True)


class LeadOrgEenheidSummary(BaseModel):
    id: UUID
    naam: str
    type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadExterneOrgSummary(BaseModel):
    id: UUID
    naam: str
    type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadAttachmentResponse(BaseModel):
    id: UUID
    lead_id: UUID
    bestandsnaam: str
    content_type: str
    bestandsgrootte: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadContactResponse(BaseModel):
    id: UUID
    person_id: UUID
    person_naam: str
    rol: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadNodeResponse(BaseModel):
    id: UUID
    node_id: UUID
    node_title: str
    node_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadActivityResponse(BaseModel):
    id: UUID
    lead_id: UUID
    author_id: UUID | None = None
    author_naam: str | None = None
    content: str
    activity_type: LeadActivityType
    metadata_: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lead response (list) and detail response
# ---------------------------------------------------------------------------


class LeadResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    organization: str | None = None
    externe_organisatie_id: UUID | None = None
    externe_organisatie: LeadExterneOrgSummary | None = None
    stage: LeadStage
    assignee_id: UUID | None = None
    assignee: LeadAssigneeSummary | None = None
    organisatie_eenheid_id: UUID
    organisatie_eenheid: LeadOrgEenheidSummary | None = None
    next_action: str | None = None
    next_action_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    sort_order: int = 0
    raw_intake_text: str | None = None
    attachment_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadDetailResponse(LeadResponse):
    activities: list[LeadActivityResponse] = Field(default_factory=list)
    attachments: list[LeadAttachmentResponse] = Field(default_factory=list)
    contacts: list[LeadContactResponse] = Field(default_factory=list)
    linked_nodes: list[LeadNodeResponse] = Field(default_factory=list)


class LeadMetricsResponse(BaseModel):
    total: int
    by_stage: dict[str, int]
    stale_count: int


# ---------------------------------------------------------------------------
# Activity / contact / node create schemas
# ---------------------------------------------------------------------------


class LeadActivityCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    activity_type: LeadActivityType = LeadActivityType.note


class LeadContactCreate(BaseModel):
    person_id: UUID
    rol: str = "contactpersoon"


class LeadNodeCreate(BaseModel):
    node_id: UUID


# ---------------------------------------------------------------------------
# AI parse result
# ---------------------------------------------------------------------------


class LeadParseResult(BaseModel):
    title: str | None = None
    organization: str | None = None
    description: str | None = None
    contact_name: str | None = None
    suggested_tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class LeadTimelineEvent(BaseModel):
    """A single event on the lead timeline."""

    id: str  # activity id or "created-{lead_id}"
    lead_id: UUID
    lead_title: str
    event_type: (
        str  # "created" | "stage_change" | "note" | "meeting" | "call" | "email"
    )
    timestamp: datetime
    actor_naam: str | None = None
    content: str | None = None  # activity content or creation description
    # Stage change specific
    from_stage: str | None = None
    to_stage: str | None = None
    # Lead metadata at time of event
    organization: str | None = None
    stage: str  # current stage of the lead
    assignee_naam: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LeadTimelineResponse(BaseModel):
    events: list[LeadTimelineEvent]
    total: int
    # Aggregates for the timeline header
    earliest: datetime | None = None
    latest: datetime | None = None
