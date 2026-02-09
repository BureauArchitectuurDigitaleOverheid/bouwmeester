"""Repository for CorpusNode CRUD and graph queries.

Overrides BaseRepository.create() and update() to manage temporal records
(title, status) alongside dual-written legacy columns.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.node_status import CorpusNodeStatus
from bouwmeester.models.node_title import CorpusNodeTitle
from bouwmeester.repositories.base import BaseRepository
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

    async def get(self, id: UUID) -> CorpusNode | None:
        stmt = (
            select(CorpusNode)
            .where(CorpusNode.id == id)
            .options(
                selectinload(CorpusNode.edges_from),
                selectinload(CorpusNode.edges_to),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        node_type: str | None = None,
        *,
        active_only: bool = True,
    ) -> list[CorpusNode]:
        stmt = select(CorpusNode).offset(skip).limit(limit)
        if node_type is not None:
            stmt = stmt.where(CorpusNode.node_type == node_type)
        if active_only:
            stmt = stmt.where(CorpusNode.geldig_tot.is_(None))
        stmt = stmt.order_by(CorpusNode.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_neighbors(self, id: UUID) -> dict:
        """Return the node and its directly connected nodes with edges."""
        node = await self.get(id)
        if node is None:
            return {"node": None, "neighbors": []}

        # Nodes connected via edges_from (this node -> neighbor)
        stmt_from = (
            select(Edge, CorpusNode)
            .join(CorpusNode, Edge.to_node_id == CorpusNode.id)
            .where(Edge.from_node_id == id)
        )
        # Nodes connected via edges_to (neighbor -> this node)
        stmt_to = (
            select(Edge, CorpusNode)
            .join(CorpusNode, Edge.from_node_id == CorpusNode.id)
            .where(Edge.to_node_id == id)
        )

        result_from = await self.session.execute(stmt_from)
        result_to = await self.session.execute(stmt_to)

        neighbors = []
        for edge, neighbor_node in result_from.all():
            neighbors.append({"node": neighbor_node, "edge": edge})
        for edge, neighbor_node in result_to.all():
            neighbors.append({"node": neighbor_node, "edge": edge})

        return {"node": node, "neighbors": neighbors}

    async def get_graph(self, node_id: UUID, depth: int = 2) -> dict:
        """Return a subgraph around a node using a recursive CTE for BFS traversal."""
        # Use a recursive CTE to find all nodes within `depth` hops
        cte_query = text(
            """
            WITH RECURSIVE graph_walk AS (
                -- Base case: the starting node
                SELECT
                    id AS node_id,
                    0 AS level
                FROM corpus_node
                WHERE id = :start_id

                UNION

                -- Recursive case: follow edges in both directions
                SELECT
                    CASE
                        WHEN e.from_node_id = gw.node_id THEN e.to_node_id
                        ELSE e.from_node_id
                    END AS node_id,
                    gw.level + 1 AS level
                FROM graph_walk gw
                JOIN edge e ON e.from_node_id = gw.node_id
                             OR e.to_node_id = gw.node_id
                WHERE gw.level < :max_depth
            )
            SELECT DISTINCT node_id FROM graph_walk
            """
        )
        result = await self.session.execute(
            cte_query, {"start_id": str(node_id), "max_depth": depth}
        )
        node_ids = [row[0] for row in result.all()]

        if not node_ids:
            return {"nodes": [], "edges": []}

        # Fetch all nodes
        nodes_stmt = select(CorpusNode).where(CorpusNode.id.in_(node_ids))
        nodes_result = await self.session.execute(nodes_stmt)
        nodes = list(nodes_result.scalars().all())

        # Fetch all edges between these nodes
        edges_stmt = select(Edge).where(
            Edge.from_node_id.in_(node_ids),
            Edge.to_node_id.in_(node_ids),
        )
        edges_result = await self.session.execute(edges_stmt)
        edges = list(edges_result.scalars().all())

        return {"nodes": nodes, "edges": edges}

    async def count(self, node_type: str | None = None) -> int:
        stmt = select(func.count()).select_from(CorpusNode)
        if node_type is not None:
            stmt = stmt.where(CorpusNode.node_type == node_type)
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
        stmt = select(CorpusNodeTitle).where(
            CorpusNodeTitle.node_id == node_id,
            CorpusNodeTitle.geldig_tot.is_(None),
        )
        result = await self.session.execute(stmt)
        active = result.scalar_one_or_none()
        if active:
            active.geldig_tot = effective
        self.session.add(
            CorpusNodeTitle(
                node_id=node_id,
                title=new_title,
                geldig_van=effective,
            )
        )

    async def _rotate_status(
        self,
        node_id: UUID,
        new_status: str,
        effective: date,
    ) -> None:
        stmt = select(CorpusNodeStatus).where(
            CorpusNodeStatus.node_id == node_id,
            CorpusNodeStatus.geldig_tot.is_(None),
        )
        result = await self.session.execute(stmt)
        active = result.scalar_one_or_none()
        if active:
            active.geldig_tot = effective
        self.session.add(
            CorpusNodeStatus(
                node_id=node_id,
                status=new_status,
                geldig_van=effective,
            )
        )

    async def _close_all_active(
        self,
        node_id: UUID,
        end_date: date,
    ) -> None:
        """Close all active temporal records for a dissolved node."""
        for model_cls in (CorpusNodeTitle, CorpusNodeStatus):
            stmt = select(model_cls).where(
                model_cls.node_id == node_id,
                model_cls.geldig_tot.is_(None),
            )
            result = await self.session.execute(stmt)
            for record in result.scalars().all():
                record.geldig_tot = end_date
