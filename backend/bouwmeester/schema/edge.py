"""Pydantic schemas for Edge."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from bouwmeester.schema.corpus_node import CorpusNodeResponse


class EdgeBase(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    edge_type_id: str = Field(max_length=100)
    weight: float = 1.0
    description: str | None = Field(None, max_length=2000)


class EdgeCreate(EdgeBase):
    pass


class EdgeUpdate(BaseModel):
    weight: float | None = None
    description: str | None = Field(None, max_length=2000)
    edge_type_id: str | None = Field(None, max_length=100)


class EdgeResponse(EdgeBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EdgeWithNodes(EdgeResponse):
    from_node: CorpusNodeResponse
    to_node: CorpusNodeResponse
