"""Service for detecting structural gaps in policy dossiers.

Mirrors the frontend useCompletenessAnalysis logic server-side and
optionally calls the LLM for a narrative summary.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.schema.llm import (
    CorpusGapSummaryItem,
    GapItem,
)
from bouwmeester.services.llm.base import BaseLLMService, GapAnalysisResult

logger = logging.getLogger(__name__)

# Keep in sync with frontend config.ts BELEIDSKOMPAS_STEPS
BELEIDSKOMPAS_STEPS = [
    {
        "number": 1,
        "question": "Wat is het probleem?",
        "node_types": ["probleem"],
    },
    {
        "number": 2,
        "question": "Wat is het beoogde doel?",
        "node_types": ["doel"],
    },
    {
        "number": 3,
        "question": "Wat zijn opties om het doel te realiseren?",
        "node_types": ["beleidsoptie"],
    },
    {
        "number": 4,
        "question": "Wat zijn de gevolgen van deze opties?",
        "node_types": ["effect"],
    },
    {
        "number": 5,
        "question": "Wat is de voorkeursoptie?",
        "node_types": ["beleidskader", "instrument", "maatregel"],
    },
]

EDGE_TYPE_ONDERDEEL_VAN = "onderdeel_van"


class GapDetectionService:
    def __init__(
        self,
        session: AsyncSession,
        llm_service: BaseLLMService | None = None,
    ) -> None:
        self.session = session
        self.llm_service = llm_service

    async def analyze_dossier(
        self, dossier_id: str
    ) -> tuple[list[GapItem], int, int, GapAnalysisResult | None]:
        """Analyze completeness of a dossier against Beleidskompas model.

        Returns (gaps, completed_count, total_steps, llm_analysis).
        """
        dossier_uuid = uuid.UUID(dossier_id)

        # Load the dossier
        stmt = select(CorpusNode).where(CorpusNode.id == dossier_uuid)
        result = await self.session.execute(stmt)
        dossier = result.scalar_one_or_none()
        if not dossier:
            return [], 0, len(BELEIDSKOMPAS_STEPS), None

        # Find all child nodes via onderdeel_van edges
        edge_stmt = select(Edge.from_node_id).where(
            Edge.to_node_id == dossier_uuid,
            Edge.edge_type_id == EDGE_TYPE_ONDERDEEL_VAN,
        )
        edge_result = await self.session.execute(edge_stmt)
        child_ids = [row[0] for row in edge_result.all()]

        # Load child nodes
        nodes_by_type: dict[str, list] = {}
        if child_ids:
            nodes_stmt = select(CorpusNode).where(CorpusNode.id.in_(child_ids))
            nodes_result = await self.session.execute(nodes_stmt)
            for node in nodes_result.scalars().all():
                nodes_by_type.setdefault(node.node_type, []).append(node)

        # Check stakeholders
        stakeholder_stmt = select(ResourcePermission).where(
            ResourcePermission.resource_type == "corpus_node",
            ResourcePermission.resource_id == dossier_uuid,
        )
        stakeholder_result = await self.session.execute(stakeholder_stmt)
        has_stakeholders = len(stakeholder_result.all()) > 0

        # Evaluate each step
        gaps: list[GapItem] = []
        completed_count = 0

        for step in BELEIDSKOMPAS_STEPS:
            present_types = []
            missing_types = []
            for nt in step["node_types"]:
                if nodes_by_type.get(nt):
                    present_types.append(nt)
                else:
                    missing_types.append(nt)

            is_complete = len(missing_types) == 0
            if is_complete:
                completed_count += 1

            if missing_types:
                gaps.append(
                    GapItem(
                        step_number=step["number"],
                        step_question=step["question"],
                        missing_types=missing_types,
                        present_types=present_types,
                        has_stakeholders=has_stakeholders,
                    )
                )

        # Optionally generate LLM narrative
        llm_result = None
        if self.llm_service and gaps:
            gap_dicts = [g.model_dump() for g in gaps]
            llm_result = await self.llm_service.generate_gap_analysis(
                dossier_title=dossier.title,
                dossier_description=dossier.description,
                gaps=gap_dicts,
            )

        return gaps, completed_count, len(BELEIDSKOMPAS_STEPS), llm_result

    async def corpus_gap_overview(self) -> list[CorpusGapSummaryItem]:
        """Quick overview of completeness for all dossier nodes."""
        stmt = select(CorpusNode).where(CorpusNode.node_type == "dossier")
        result = await self.session.execute(stmt)
        dossiers = result.scalars().all()

        items = []
        for dossier in dossiers:
            dossier_id = str(dossier.id)
            gaps, completed, total, _ = await self.analyze_dossier(dossier_id)

            # Check stakeholders
            stakeholder_stmt = select(ResourcePermission).where(
                ResourcePermission.resource_type == "corpus_node",
                ResourcePermission.resource_id == dossier.id,
            )
            stakeholder_result = await self.session.execute(stakeholder_stmt)
            has_stakeholders = len(stakeholder_result.all()) > 0

            items.append(
                CorpusGapSummaryItem(
                    dossier_id=dossier_id,
                    dossier_title=dossier.title,
                    completed_count=completed,
                    total_steps=total,
                    has_stakeholders=has_stakeholders,
                )
            )

        return items
