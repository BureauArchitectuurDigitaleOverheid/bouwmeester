"""API routes for omni full-text search."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.repositories.search import SearchRepository
from bouwmeester.schema.search import (
    SearchResponse,
    SearchResult,
    SearchResultType,
    SimilarNodeItem,
    SimilarNodesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    current_user: OptionalUser,
    q: str = Query(..., min_length=1, max_length=500),
    result_types: list[SearchResultType] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> SearchResponse:
    """Full-text search across nodes, tasks, people, and org units."""
    repo = SearchRepository(db)
    type_values = [rt.value for rt in result_types] if result_types else None
    results = await repo.full_text_search(
        query=q,
        result_types=type_values,
        limit=limit,
        org_ctx=org_ctx,
    )
    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        total=len(results),
        query=q,
    )


@router.get("/similar-nodes", response_model=SimilarNodesResponse)
async def find_similar_nodes(
    current_user: OptionalUser,
    title: str = Query(..., min_length=3, max_length=500),
    exclude_id: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> SimilarNodesResponse:
    """Find corpus nodes with similar titles (trigram + FTS)."""
    repo = SearchRepository(db)
    items = await repo.find_similar_nodes(
        title=title,
        exclude_node_id=exclude_id,
        limit=limit,
    )
    return SimilarNodesResponse(items=[SimilarNodeItem(**i) for i in items])
