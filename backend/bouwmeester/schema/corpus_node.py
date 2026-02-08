"""Pydantic schemas for CorpusNode."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bouwmeester.schema.edge import EdgeResponse


class NodeType(enum.StrEnum):
    dossier = "dossier"
    doel = "doel"
    instrument = "instrument"
    beleidskader = "beleidskader"
    maatregel = "maatregel"
    politieke_input = "politieke_input"
    probleem = "probleem"
    effect = "effect"
    beleidsoptie = "beleidsoptie"


class CorpusNodeBase(BaseModel):
    title: str
    description: str | None = None
    node_type: NodeType
    status: str = "actief"


class CorpusNodeCreate(CorpusNodeBase):
    pass


class CorpusNodeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None


class CorpusNodeResponse(CorpusNodeBase):
    id: UUID
    created_at: datetime
    updated_at: datetime | None = None
    edge_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class CorpusNodeWithEdges(CorpusNodeResponse):
    edges_from: list["EdgeResponse"] = []
    edges_to: list["EdgeResponse"] = []
