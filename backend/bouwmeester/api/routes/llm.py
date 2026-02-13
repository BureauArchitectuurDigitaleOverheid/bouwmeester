"""API routes for LLM-powered features: tag suggestions, edge suggestions, summaries.

These endpoints send corpus node titles, descriptions, and tag names to the LLM.
This is policy content (PUBLIC sensitivity), not PII, so any configured provider
(Claude or VLAM) may be used.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.llm import (
    EdgeSuggestionRequest,
    EdgeSuggestionResponse,
    SummarizeRequest,
    SummarizeResponse,
    TagSuggestionRequest,
    TagSuggestionResponse,
)
from bouwmeester.services.llm import get_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/suggest-tags", response_model=TagSuggestionResponse)
async def suggest_tags(
    request: TagSuggestionRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> TagSuggestionResponse:
    """Suggest tags for a corpus node based on title and description."""
    service = await get_llm_service(db)
    if not service:
        return TagSuggestionResponse(
            matched_tags=[], suggested_new_tags=[], available=False
        )

    tag_repo = TagRepository(db)
    all_tags = await tag_repo.get_all()
    tag_names = [t.name for t in all_tags]

    result = await service.suggest_tags(
        title=request.title,
        description=request.description,
        node_type=request.node_type,
        bestaande_tags=tag_names,
    )
    return TagSuggestionResponse(
        matched_tags=result.matched_tags,
        suggested_new_tags=result.suggested_new_tags,
    )


@router.post("/suggest-edges", response_model=EdgeSuggestionResponse)
async def suggest_edges(
    request: EdgeSuggestionRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeSuggestionResponse:
    """Suggest related nodes for a given corpus node."""
    from bouwmeester.services.edge_suggestion_service import EdgeSuggestionService

    service = await get_llm_service(db)
    if not service:
        return EdgeSuggestionResponse(suggestions=[], available=False)

    edge_service = EdgeSuggestionService(db, service)
    suggestions = await edge_service.suggest_edges(request.node_id)
    return EdgeSuggestionResponse(suggestions=suggestions)


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(
    request: SummarizeRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> SummarizeResponse:
    """Summarize a long text."""
    service = await get_llm_service(db)
    if not service:
        return SummarizeResponse(summary="", available=False)

    result = await service.summarize(
        text=request.text,
        max_words=request.max_words,
    )
    return SummarizeResponse(summary=result.summary)
