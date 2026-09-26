"""Repository for CorpusNode CRUD and graph queries.

Overrides BaseRepository.create() and update() to manage temporal records
(title, status) alongside dual-written legacy columns.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.org_context import OrgContext, apply_org_filter
from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.node_status import CorpusNodeStatus
from bouwmeester.models.node_title import CorpusNodeTitle
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.repositories.graph_filters import exclude_unconnected_pi
from bouwmeester.repositories.temporal import (
    close_active_records,
    rotate_temporal_record,
)
from bouwmeester.schema.corpus_node import CorpusNodeCreate, CorpusNodeUpdate


class CorpusNodeRepository(BaseRepository[CorpusNode]):
    model = CorpusNode

    # ------------------------------------------------------------------
    # Create / Update (temporal-aware overrides)
    # ------------------------------------------------------------------

    async def create(self, data: CorpusNodeCreate) -> CorpusNode:
        effective = data.geldig_van or date.today()
        node = CorpusNode(
            title=data.title,
            node_type=data.node_type,
            description=data.description,
            status=data.status,
            geldig_van=effective,
        )
        self.session.add(node)
        await self.session.flush()

        # Temporal title record
        self.session.add(
            CorpusNodeTitle(
                node_id=node.id,
                title=data.title,
                geldig_van=effective,
            )
        )
        # Temporal status record
        self.session.add(
            CorpusNodeStatus(
                node_id=node.id,
                status=data.status,
                geldig_van=effective,
            )
        )

        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def update(
        self,
        id: UUID,
        data: CorpusNodeUpdate,
    ) -> CorpusNode | None:
        node = await self.session.get(CorpusNode, id)
        if node is None:
            return None

        changes = data.model_dump(exclude_unset=True)
        effective = changes.pop("wijzig_datum", None) or date.today()

        # Dissolution: close all active temporal records
        if "geldig_tot" in changes:
            end = changes["geldig_tot"]
            node.geldig_tot = end
            await self._close_all_active(node.id, end)

        # Title change
        if "title" in changes and changes["title"] != node.title:
            await self._rotate_title(node.id, changes["title"], effective)
            node.title = changes["title"]

        # Status change
        if "status" in changes and changes["status"] != node.status:
            await self._rotate_status(node.id, changes["status"], effective)
            node.status = changes["status"]

        # Simple field updates
        if "description" in changes:
            node.description = changes["description"]

        await self.session.flush()
        await self.session.refresh(node)
        return node

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(
        self,
        id: UUID,
        org_ctx: OrgContext | None = None,
    ) -> CorpusNode | None:
        stmt = (
            select(CorpusNode)
            .where(CorpusNode.id == id)
            .options(
                selectinload(CorpusNode.edges_from),
                selectinload(CorpusNode.edges_to),
            )
        )
        stmt = apply_org_filter(stmt, CorpusNode.organisatie_eenheid_id, org_ctx)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        node_type: str | None = None,
        *,
        search: str | None = None,
        active_only: bool = True,
        include_unconnected_pi: bool = False,
        org_ctx: OrgContext | None = None,
    ) -> list[CorpusNode]:
        stmt = select(CorpusNode)
        if node_type is not None:
            stmt = stmt.where(CorpusNode.node_type == node_type)
        if search:
            escaped = escape_like(search)
            stmt = stmt.where(CorpusNode.title.ilike(f"%{escaped}%", escape="\\"))
        if active_only:
            stmt = stmt.where(CorpusNode.geldig_tot.is_(None))

        # Exclude unconnected politieke_input nodes at the SQL level so
        # pagination (offset/limit) remains correct.
        if not include_unconnected_pi and (
            node_type is None or node_type == "politieke_input"
        ):
            stmt = stmt.where(exclude_unconnected_pi())

        stmt = apply_org_filter(stmt, CorpusNode.organisatie_eenheid_id, org_ctx)
        # Alphabetical by title: this is the generic node list used by
        # selection dropdowns (e.g. the Opdracht instrument picker), where
        # alphabetical order is what users expect, not creation order.
        stmt = stmt.order_by(CorpusNode.title.asc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_beleidskompas_progress(
        self,
        dossier_ids: list[UUID],
    ) -> dict[UUID, tuple[int, int]]:
        """Return beleidskompas progress for a list of dossier node IDs.

        For each dossier, counts child node types connected via
        ``onderdeel_van`` edges and checks against the 5 KCBR steps.

        Returns a dict mapping dossier_id → (completed_steps, total_steps).
        """
        if not dossier_ids:
            return {}

        # The 5 KCBR steps and their required node types.
        # A step is complete when every node type in it has ≥1 child node.
        # NOTE: keep in sync with frontend/src/components/nodes/beleidskompas/config.ts
        kcbr_steps: list[list[str]] = [
            ["probleem"],
            ["doel"],
            ["beleidsoptie"],
            ["effect"],
            ["beleidskader", "instrument", "maatregel"],
        ]
        total_steps = len(kcbr_steps)

        # Query: for each dossier, get the set of child node_types
        # via onderdeel_van edges (child.from_node_id → dossier.to_node_id).
        stmt = (
            select(
                Edge.to_node_id.label("dossier_id"),
                CorpusNode.node_type,
            )
            .join(CorpusNode, Edge.from_node_id == CorpusNode.id)
            .where(
                Edge.to_node_id.in_(dossier_ids),
                Edge.edge_type_id == "onderdeel_van",
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        # Group node types by dossier
        types_by_dossier: dict[UUID, set[str]] = {}
        for row in rows:
            did = UUID(str(row.dossier_id))
            types_by_dossier.setdefault(did, set()).add(row.node_type)

        progress: dict[UUID, tuple[int, int]] = {}
        for did in dossier_ids:
            present_types = types_by_dossier.get(did, set())
            completed = sum(
                1
                for step_types in kcbr_steps
                if all(nt in present_types for nt in step_types)
            )
            progress[did] = (completed, total_steps)

        return progress

    async def count(
        self,
        node_type: str | None = None,
        org_ctx: OrgContext | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(CorpusNode)
        if node_type is not None:
            stmt = stmt.where(CorpusNode.node_type == node_type)
        stmt = apply_org_filter(stmt, CorpusNode.organisatie_eenheid_id, org_ctx)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # History queries
    # ------------------------------------------------------------------

    async def get_title_history(
        self,
        node_id: UUID,
    ) -> list[CorpusNodeTitle]:
        stmt = (
            select(CorpusNodeTitle)
            .where(CorpusNodeTitle.node_id == node_id)
            .order_by(
                CorpusNodeTitle.geldig_van.desc(),
                CorpusNodeTitle.geldig_tot.asc().nulls_first(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_status_history(
        self,
        node_id: UUID,
    ) -> list[CorpusNodeStatus]:
        stmt = (
            select(CorpusNodeStatus)
            .where(CorpusNodeStatus.node_id == node_id)
            .order_by(
                CorpusNodeStatus.geldig_van.desc(),
                CorpusNodeStatus.geldig_tot.asc().nulls_first(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Private temporal helpers
    # ------------------------------------------------------------------

    async def _rotate_title(
        self,
        node_id: UUID,
        new_title: str,
        effective: date,
    ) -> None:
        await rotate_temporal_record(
            self.session,
            CorpusNodeTitle,
            CorpusNodeTitle.node_id,
            node_id,
            effective,
            CorpusNodeTitle(node_id=node_id, title=new_title, geldig_van=effective),
        )

    async def _rotate_status(
        self,
        node_id: UUID,
        new_status: str,
        effective: date,
    ) -> None:
        await rotate_temporal_record(
            self.session,
            CorpusNodeStatus,
            CorpusNodeStatus.node_id,
            node_id,
            effective,
            CorpusNodeStatus(node_id=node_id, status=new_status, geldig_van=effective),
        )

    async def _close_all_active(
        self,
        node_id: UUID,
        end_date: date,
    ) -> None:
        """Close all active temporal records for a dissolved node."""
        await close_active_records(
            self.session,
            [
                (CorpusNodeTitle, CorpusNodeTitle.node_id),
                (CorpusNodeStatus, CorpusNodeStatus.node_id),
            ],
            node_id,
            end_date,
        )
