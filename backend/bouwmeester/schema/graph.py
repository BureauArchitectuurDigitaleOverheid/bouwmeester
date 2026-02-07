"""Pydantic schemas for graph-related operations."""

from pydantic import BaseModel

from bouwmeester.schema.corpus_node import CorpusNodeResponse, NodeType
from bouwmeester.schema.edge import EdgeResponse


class NeighborEntry(BaseModel):
    node: CorpusNodeResponse
    edge: EdgeResponse


class GraphNeighborsResponse(BaseModel):
    node: CorpusNodeResponse
    neighbors: list[NeighborEntry]


class GraphSearchParams(BaseModel):
    query: str | None = None
    node_types: list[NodeType] | None = None
    limit: int = 50


class GraphViewResponse(BaseModel):
    nodes: list[CorpusNodeResponse]
    edges: list[EdgeResponse]
