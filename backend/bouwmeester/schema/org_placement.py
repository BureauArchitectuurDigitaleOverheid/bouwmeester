"""Pydantic schemas for org placement requests."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlacementStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class OrgPlacementRequestCreate(BaseModel):
    organisatie_eenheid_id: UUID


class OrgPlacementRequestDecision(BaseModel):
    status: PlacementStatus


class OrgPlacementRequestResponse(BaseModel):
    id: UUID
    person_id: UUID
    person_naam: str
    organisatie_eenheid_id: UUID
    eenheid_naam: str
    status: str
    requested_at: datetime
    decided_at: datetime | None = None
    decided_by: UUID | None = None

    model_config = ConfigDict(from_attributes=True)
