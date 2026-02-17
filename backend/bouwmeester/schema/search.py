"""Pydantic schemas for omni-search."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SearchResultType(StrEnum):
    corpus_node = "corpus_node"
    task = "task"
    person = "person"
    organisatie_eenheid = "organisatie_eenheid"
    parlementair_item = "parlementair_item"
    tag = "tag"


class SearchResult(BaseModel):
    id: UUID
    result_type: SearchResultType
    title: str
    subtitle: str | None = None
    description: str | None = None
    score: float
    highlights: list[str] | None = None
    url: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str


# --- Similar Nodes (A3: Duplicate Detection) ---


class SimilarNodeItem(BaseModel):
    id: UUID
    title: str
    node_type: str
    similarity: float


class SimilarNodesResponse(BaseModel):
    items: list[SimilarNodeItem]


# --- Natural Language Search (B5) ---


class NlSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)


class SearchInterpretation(BaseModel):
    search_terms: list[str]
    node_types: list[str] = []
    tags: list[str] = []
    original_query: str


class NlSearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str
    interpretation: SearchInterpretation | None = None
    available: bool = True
