"""Repository for CorpusNode CRUD and graph queries."""

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.schema.corpus_node import CorpusNodeCreate, CorpusNodeUpdate


class CorpusNodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
    ) -> list[CorpusNode]:
        stmt = select(CorpusNode).offset(skip).limit(limit)
        if node_type is not None:
            stmt = stmt.where(CorpusNode.node_type == node_type)
        stmt = stmt.order_by(CorpusNode.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: CorpusNodeCreate) -> CorpusNode:
        node = CorpusNode(**data.model_dump())
        self.session.add(node)
        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def update(self, id: UUID, data: CorpusNodeUpdate) -> CorpusNode | None:
        node = await self.session.get(CorpusNode, id)
        if node is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(node, key, value)
        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def delete(self, id: UUID) -> bool:
        node = await self.session.get(CorpusNode, id)
        if node is None:
            return False
        await self.session.delete(node)
        await self.session.flush()
        return True

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
