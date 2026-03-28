"""Pydantic schemas for cross-org shared access grants."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class SharedAccessCreate(BaseModel):
    source_node_id: UUID | None = None
    source_eenheid_id: UUID | None = None
    target_eenheid_id: UUID
    access_level: Literal["read", "edit"]
    reason: str | None = None
    geldig_van: date | None = None
    geldig_tot: date | None = None

    @model_validator(mode="after")
    def check_source(self) -> "SharedAccessCreate":
        if self.source_node_id is None and self.source_eenheid_id is None:
            msg = "Either source_node_id or source_eenheid_id must be set"
            raise ValueError(msg)
        if self.source_node_id is not None and self.source_eenheid_id is not None:
            msg = "Only one of source_node_id or source_eenheid_id can be set"
            raise ValueError(msg)
        return self


class SharedAccessResponse(BaseModel):
    id: UUID
    source_node_id: UUID | None = None
    source_eenheid_id: UUID | None = None
    source_eenheid_naam: str | None = None
    target_eenheid_id: UUID
    target_eenheid_naam: str | None = None
    access_level: str
    shared_by_id: UUID | None = None
    reason: str | None = None
    geldig_van: date
    geldig_tot: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
