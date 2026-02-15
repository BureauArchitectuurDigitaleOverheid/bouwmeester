"""Pydantic schemas for Mattermost integration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class MattermostLinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class MattermostVerifyLinkRequest(BaseModel):
    code: str
    mattermost_user_id: str
    mattermost_username: str
