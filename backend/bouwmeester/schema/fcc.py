"""Pydantic schemas for FCC (Fortes Change Cloud) sync endpoints."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SyncStatus(enum.StrEnum):
    synced = "synced"
    pending_push = "pending_push"
    pending_pull = "pending_pull"
    conflict = "conflict"
    error = "error"


class SyncDirection(enum.StrEnum):
    inbound = "inbound"
    outbound = "outbound"
    bidirectional = "bidirectional"


class FccConflictResolution(enum.StrEnum):
    use_ours = "use_ours"
    use_theirs = "use_theirs"


class FccSyncTriggerResponse(BaseModel):
    pulled: int
    pushed: int
    contacts_matched: int = 0


class FccSyncLogResponse(BaseModel):
    id: UUID
    opdracht_id: UUID | None = None
    direction: str
    action: str
    details: dict | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FccSchemaResponse(BaseModel):
    entity_sets: dict[str, list[str]]


class FccConflictResolveRequest(BaseModel):
    resolution: FccConflictResolution
