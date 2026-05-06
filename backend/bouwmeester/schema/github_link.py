"""Pydantic-schema's voor GitHubLink."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GitHubLinkType(enum.StrEnum):
    branch = "branch"
    pull_request = "pull_request"
    issue = "issue"
    repo = "repo"
    workflow_run = "workflow_run"
    other = "other"


class GitHubLinkCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=1000)
    title: str | None = Field(None, max_length=500)


class GitHubLinkUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)


class GitHubLinkResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    url: str
    link_type: GitHubLinkType
    owner: str
    repo: str
    ref: str | None = None
    title: str | None = None
    created_by_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
