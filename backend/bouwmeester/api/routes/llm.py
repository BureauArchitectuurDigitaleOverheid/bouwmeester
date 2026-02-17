"""API routes for LLM-powered features: tag suggestions, edge suggestions, summaries.

Most endpoints send corpus node titles, descriptions, and tag names to the LLM.
This is internal policy content (INTERNAL sensitivity), requiring a provider that
supports that level (i.e. VLAM). Only parliamentary data is PUBLIC.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.llm import (
    CorpusGapOverviewResponse,
    EdgeSuggestionRequest,
    EdgeSuggestionResponse,
    GapAnalysisRequest,
    GapAnalysisResponse,
    KompasGuidanceRequest,
    KompasGuidanceResponse,
    SummarizeRequest,
    SummarizeResponse,
    TagSuggestionRequest,
    TagSuggestionResponse,
    TaskSuggestionRequest,
    TaskSuggestionResponse,
)
from bouwmeester.services.llm import get_llm_service_for
from bouwmeester.services.llm.base import DataSensitivity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/suggest-tags", response_model=TagSuggestionResponse)
async def suggest_tags(
    request: TagSuggestionRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> TagSuggestionResponse:
    """Suggest tags for a corpus node based on title and description."""
    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
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

    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
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
    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    if not service:
        return SummarizeResponse(summary="", available=False)

    result = await service.summarize(
        text=request.text,
        max_words=request.max_words,
    )
    return SummarizeResponse(summary=result.summary)


@router.post("/suggest-task", response_model=TaskSuggestionResponse)
async def suggest_task(
    request: TaskSuggestionRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> TaskSuggestionResponse:
    """Suggest task title and description based on a node."""
    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    if not service:
        return TaskSuggestionResponse(title="", description="", available=False)

    result = await service.suggest_task(
        node_title=request.node_title,
        node_description=request.node_description,
        node_type=request.node_type,
    )
    return TaskSuggestionResponse(
        title=result.title,
        description=result.description,
    )


@router.post("/gap-analysis", response_model=GapAnalysisResponse)
async def gap_analysis(
    request: GapAnalysisRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> GapAnalysisResponse:
    """Analyze completeness of a dossier against the Beleidskompas model."""
    from bouwmeester.services.gap_detection_service import GapDetectionService

    llm_service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    gap_service = GapDetectionService(db, llm_service)
    gaps, completed, total, llm_result = await gap_service.analyze_dossier(
        request.dossier_id
    )

    return GapAnalysisResponse(
        gaps=gaps,
        completed_count=completed,
        total_steps=total,
        narrative=llm_result.narrative if llm_result else "",
        recommendations=llm_result.recommendations if llm_result else [],
        available=llm_service is not None,
    )


@router.get("/corpus-gaps", response_model=CorpusGapOverviewResponse)
async def corpus_gap_overview(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> CorpusGapOverviewResponse:
    """Overview of completeness for all dossier nodes."""
    from bouwmeester.services.gap_detection_service import GapDetectionService

    gap_service = GapDetectionService(db)
    items = await gap_service.corpus_gap_overview()
    return CorpusGapOverviewResponse(items=items, total=len(items))


@router.post("/kompas-guidance", response_model=KompasGuidanceResponse)
async def kompas_guidance(
    request: KompasGuidanceRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> KompasGuidanceResponse:
    """Suggest existing nodes to link for incomplete Beleidskompas steps."""
    from bouwmeester.services.edge_suggestion_service import EdgeSuggestionService

    service = await get_llm_service_for(DataSensitivity.INTERNAL, db)
    if not service:
        return KompasGuidanceResponse(suggestions=[], available=False)

    edge_service = EdgeSuggestionService(db, service)
    suggestions = await edge_service.suggest_kompas_links(
        dossier_id=request.dossier_id,
        step_node_types=request.step_node_types,
        step_description=request.step_description,
        max_candidates=request.max_candidates,
    )
    return KompasGuidanceResponse(suggestions=suggestions)
