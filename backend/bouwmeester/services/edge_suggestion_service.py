"""Service for suggesting edges between corpus nodes.

Uses tag overlap (fast, no LLM) to find candidates, then LLM scoring
for content relevance.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.tag import NodeTag
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.llm import EdgeSuggestionItem
from bouwmeester.services.llm.base import BaseLLMService, EdgeRelevanceResult

logger = logging.getLogger(__name__)

# Overall timeout for all LLM scoring calls combined.
LLM_SCORING_TIMEOUT_SECONDS = 30


class EdgeSuggestionService:
    """Orchestrates tag-overlap + LLM scoring for edge suggestions."""

    def __init__(self, session: AsyncSession, llm_service: BaseLLMService) -> None:
        self.session = session
        self.llm_service = llm_service
        self.tag_repo = TagRepository(session)

    async def suggest_edges(
        self,
        node_id: str,
        max_candidates: int = 10,
        max_llm_scored: int = 5,
    ) -> list[EdgeSuggestionItem]:
        """Find and score related nodes for the given node."""
        node_uuid = uuid.UUID(node_id)

        # Get the source node
        stmt = select(CorpusNode).where(CorpusNode.id == node_uuid)
        result = await self.session.execute(stmt)
        source_node = result.scalar_one_or_none()
        if not source_node:
            return []

        # Get the source node's tags
        node_tags = await self.tag_repo.get_by_node(node_uuid)
        if not node_tags:
            return []

        tag_ids = {nt.tag_id for nt in node_tags}

        # Also include parent tags for broader matching
        tag_objects = await self.tag_repo.get_all()
        tag_by_id = {t.id: t for t in tag_objects}
        all_tag_ids = set(tag_ids)
        for tid in tag_ids:
            tag = tag_by_id.get(tid)
            if tag and tag.parent_id:
                all_tag_ids.add(tag.parent_id)

        # Find other nodes sharing these tags
        tag_node_stmt = select(NodeTag.tag_id, NodeTag.node_id).where(
            NodeTag.tag_id.in_(all_tag_ids),
            NodeTag.node_id != node_uuid,
        )
        tag_node_result = await self.session.execute(tag_node_stmt)

        node_scores: dict[uuid.UUID, float] = {}
        for row_tag_id, row_node_id in tag_node_result.all():
            weight = 1.0 if row_tag_id in tag_ids else 0.7
            node_scores[row_node_id] = node_scores.get(row_node_id, 0.0) + weight

        if not node_scores:
            return []

        # Sort by overlap score, take top candidates
        sorted_candidates = sorted(
            node_scores.items(), key=lambda x: x[1], reverse=True
        )[:max_candidates]

        # Load candidate nodes
        candidate_ids = [nid for nid, _ in sorted_candidates]
        nodes_stmt = select(CorpusNode).where(CorpusNode.id.in_(candidate_ids))
        nodes_result = await self.session.execute(nodes_stmt)
        nodes_by_id = {n.id: n for n in nodes_result.scalars().all()}

        # LLM-score top candidates concurrently with overall timeout
        to_score = []
        for nid, _overlap_score in sorted_candidates[:max_llm_scored]:
            target = nodes_by_id.get(nid)
            if target:
                to_score.append((nid, target))

        if not to_score:
            return []

        async def _score_one(
            nid: uuid.UUID, target: CorpusNode
        ) -> tuple[uuid.UUID, CorpusNode, EdgeRelevanceResult | None]:
            try:
                r = await self.llm_service.score_edge_relevance(
                    source_title=source_node.title,
                    source_description=source_node.description,
                    target_title=target.title,
                    target_description=target.description,
                )
                return nid, target, r
            except Exception:
                logger.exception("LLM scoring failed for edge to %s", nid)
                return nid, target, None

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[_score_one(nid, t) for nid, t in to_score]),
                timeout=LLM_SCORING_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "LLM edge scoring timed out after %ds",
                LLM_SCORING_TIMEOUT_SECONDS,
            )
            return []

        suggestions: list[EdgeSuggestionItem] = []
        for nid, target, llm_result in results:
            if llm_result is None or llm_result.score < 0.3:
                continue
            suggestions.append(
                EdgeSuggestionItem(
                    target_node_id=str(nid),
                    target_node_title=target.title,
                    target_node_type=target.node_type,
                    confidence=llm_result.score,
                    suggested_edge_type=llm_result.suggested_edge_type,
                    reason=llm_result.reason,
                )
            )

        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions
