"""Pydantic schemas for search."""

from uuid import UUID

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: UUID
    node_type: str
    title: str
    description: str | None = None
    rank: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str
