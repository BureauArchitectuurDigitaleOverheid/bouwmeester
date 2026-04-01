"""Pydantic schemas for Mattermost integration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MattermostUserResponse(BaseModel):
    id: UUID
    person_id: UUID
    mattermost_user_id: str
    mattermost_username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MattermostLinkStatusResponse(BaseModel):
    linked: bool
    mattermost_username: str | None = None
    bot_dm_url: str | None = None


class MattermostLinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class MattermostVerifyLinkRequest(BaseModel):
    code: str = Field(..., pattern=r"^BM-[a-z0-9]{6,12}$", max_length=15)
    mattermost_user_id: str = Field(..., pattern=r"^[a-zA-Z0-9]{26}$", max_length=26)
    mattermost_username: str = Field(..., min_length=1, max_length=255)

    @field_validator("mattermost_username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip()
