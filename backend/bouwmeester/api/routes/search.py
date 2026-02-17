"""API routes for omni full-text search."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.search import SearchRepository
from bouwmeester.schema.search import (
    NlSearchRequest,
    NlSearchResponse,
    SearchInterpretation,
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
) -> SearchResponse:
    """Full-text search across nodes, tasks, people, and org units."""
    repo = SearchRepository(db)
    type_values = [rt.value for rt in result_types] if result_types else None
    results = await repo.full_text_search(
        query=q,
        result_types=type_values,
        limit=limit,
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


@router.post("/nl", response_model=NlSearchResponse)
async def natural_language_search(
    request: NlSearchRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> NlSearchResponse:
    """AI-powered natural language search: interprets query, then runs FTS."""
    from bouwmeester.repositories.tag import TagRepository
    from bouwmeester.services.llm import get_llm_service_for
    from bouwmeester.services.llm.base import DataSensitivity

    repo = SearchRepository(db)
    tag_repo = TagRepository(db)

    # Try AI interpretation
    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    if not service:
        # Fallback to plain FTS
        results = await repo.full_text_search(query=request.query, limit=50)
        return NlSearchResponse(
            results=[SearchResult(**r) for r in results],
            total=len(results),
            query=request.query,
            interpretation=None,
            available=False,
        )

    all_tags = await tag_repo.get_all()
    tag_names = [t.name for t in all_tags]
    node_types = [
        "dossier", "doel", "instrument", "beleidskader",
        "maatregel", "politieke_input", "probleem", "effect", "beleidsoptie",
    ]

    try:
        interpretation_result = await service.interpret_search_query(
            query=request.query,
            available_node_types=node_types,
            available_tags=tag_names,
        )

        # Build effective search from interpretation
        effective_query = " ".join(interpretation_result.search_terms) or request.query
        result_types = interpretation_result.node_types or None

        results = await repo.full_text_search(
            query=effective_query,
            result_types=["corpus_node"] if result_types else None,
            limit=50,
        )

        interpretation = SearchInterpretation(
            search_terms=interpretation_result.search_terms,
            node_types=interpretation_result.node_types,
            tags=interpretation_result.tags,
            original_query=request.query,
        )

        return NlSearchResponse(
            results=[SearchResult(**r) for r in results],
            total=len(results),
            query=request.query,
            interpretation=interpretation,
        )
    except Exception:
        logger.exception("NL search interpretation failed, falling back to FTS")
        results = await repo.full_text_search(query=request.query, limit=50)
        return NlSearchResponse(
            results=[SearchResult(**r) for r in results],
            total=len(results),
            query=request.query,
            interpretation=None,
            available=False,
        )
