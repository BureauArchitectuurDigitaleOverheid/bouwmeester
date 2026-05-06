"""Pydantic-schema's voor MattermostChannelLink."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MattermostChannelSearchResult(BaseModel):
    """Resultaat van een MM-kanaal-zoekopdracht via de bot."""

    channel_id: str
    channel_name: str
    channel_display_name: str
    team_id: str | None = None
    member_count: int | None = None
    is_bot_member: bool = False


class MattermostChannelLinkCreate(BaseModel):
    channel_id: str = Field(..., pattern=r"^[a-z0-9]{26}$")
    channel_name: str = Field(..., min_length=1, max_length=255)
    channel_display_name: str = Field(..., min_length=1, max_length=255)
    team_id: str | None = Field(None, pattern=r"^[a-z0-9]{26}$")
    auto_note_enabled: bool | None = None
    suggest_leads_enabled: bool | None = None


class MattermostChannelLinkUpdate(BaseModel):
    auto_note_enabled: bool | None = None
    suggest_leads_enabled: bool | None = None


class MattermostChannelLinkResponse(BaseModel):
    id: UUID
    channel_id: str
    channel_name: str
    channel_display_name: str
    team_id: str | None
    scope_type: str
    scope_id: UUID
    auto_note_enabled: bool
    suggest_leads_enabled: bool
    last_seen_post_at: int | None
    disabled_at: datetime | None
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
