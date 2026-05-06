"""Pydantic-schemas voor SuggestedLead (Mattermost-suggesties)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SuggestedLeadResponse(BaseModel):
    id: UUID
    source_type: str
    source_post_id: str
    source_channel_id: str
    initiatief_id: UUID
    proposed_title: str
    proposed_description: str | None
    raw_text: str | None
    confidence: float | None
    reasoning: str | None
    match_existing_lead_id: UUID | None
    status: str
    mm_thread_post_id: str | None
    approved_lead_id: UUID | None
    reviewed_at: datetime | None
    reviewed_by_id: UUID | None
    review_source: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
