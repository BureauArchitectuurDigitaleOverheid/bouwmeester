"""Pydantic schemas for Edge."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from bouwmeester.schema.corpus_node import CorpusNodeResponse


class EdgeBase(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    edge_type_id: str
    weight: float = 1.0
    description: str | None = None


class EdgeCreate(EdgeBase):
    pass


class EdgeUpdate(BaseModel):
    weight: float | None = None
    description: str | None = None
    edge_type_id: str | None = None


class EdgeResponse(EdgeBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EdgeWithNodes(EdgeResponse):
    from_node: CorpusNodeResponse
    to_node: CorpusNodeResponse
