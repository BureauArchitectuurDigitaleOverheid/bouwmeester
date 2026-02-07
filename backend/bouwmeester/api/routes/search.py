"""API routes for full-text search."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.repositories.search import SearchRepository
from bouwmeester.schema.corpus_node import NodeType
from bouwmeester.schema.search import SearchResponse, SearchResult

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    node_types: list[NodeType] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    repo = SearchRepository(db)
    type_values = [nt.value for nt in node_types] if node_types else None
    results = await repo.full_text_search(
        query=q,
        node_types=type_values,
        limit=limit,
    )
    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        total=len(results),
        query=q,
    )
