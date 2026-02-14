"""Pydantic schemas for ParlementairItem and SuggestedEdge."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from bouwmeester.schema.corpus_node import CorpusNodeResponse


class SuggestedEdgeResponse(BaseModel):
    id: UUID
    parlementair_item_id: UUID
    target_node_id: UUID
    target_node: CorpusNodeResponse | None = None
    edge_type_id: str
    confidence: float
    reason: str | None = None
    status: str
    edge_id: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ParlementairItemResponse(BaseModel):
    id: UUID
    type: str
    zaak_id: str
    zaak_nummer: str
    titel: str
    onderwerp: str
    bron: str
    datum: date | None = None
    status: str
    corpus_node_id: UUID | None = None
    indieners: list[str] | None = None
    document_tekst: str | None = None
    document_url: str | None = None
    llm_samenvatting: str | None = None
    matched_tags: list[str] | None = None
    deadline: date | None = None
    ministerie: str | None = None
    extra_data: dict | None = None
    imported_at: datetime | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    suggested_edges: list[SuggestedEdgeResponse] = []

    @field_validator("datum", "deadline", mode="before")
    @classmethod
    def _nullify_sentinel_dates(cls, v: date | None) -> date | None:
        """TK API uses 0001-01-01 as sentinel for missing dates."""
        if v is not None and hasattr(v, "year") and v.year <= 1:
            return None
        return v

    model_config = ConfigDict(from_attributes=True)


class ReviewAction(BaseModel):
    """Used when reviewing/approving/rejecting suggested edges."""

    status: str  # "approved" | "rejected"
