"""Pydantic schemas for omni-search."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


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
