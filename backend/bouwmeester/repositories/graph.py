"""Repository for graph-wide queries (path-finding, full graph)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge


class GraphRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Path finding -- shortest path via recursive CTE (BFS)
    # ------------------------------------------------------------------

    async def find_path(
        self,
        from_id: UUID,
        to_id: UUID,
        max_depth: int = 10,
    ) -> list[dict]:
        """Find the shortest path between two nodes using a recursive CTE.

        The CTE performs a breadth-first search over the ``edge`` table,
        treating edges as *undirected* (traversable in both directions).
        It returns one row per step with the full path encoded as arrays
        so we can reconstruct the route.

        Returns a list of dicts -- one per step -- each containing:
          - ``node_id``, ``node_title``, ``node_type``
          - ``edge_id``, ``edge_type_id`` (``None`` for the starting node)
        """
        query = text(
            """
            WITH RECURSIVE path_walk AS (
                -- Base: start from the source node.
                SELECT
                    cn.id        AS node_id,
                    cn.title     AS node_title,
                    cn.node_type AS node_type,
                    NULL::uuid   AS edge_id,
                    NULL::text   AS edge_type_id,
                    ARRAY[cn.id] AS visited,
                    0            AS depth
                FROM corpus_node cn
                WHERE cn.id = :from_id

                UNION ALL

                -- Recursive: follow edges in both directions.
                SELECT
                    next_node.id,
                    next_node.title,
                    next_node.node_type,
                    e.id,
                    e.edge_type_id,
                    pw.visited || next_node.id,
                    pw.depth + 1
                FROM path_walk pw
                JOIN edge e
                    ON (e.from_node_id = pw.node_id OR e.to_node_id = pw.node_id)
                JOIN corpus_node next_node
                    ON next_node.id = CASE
                        WHEN e.from_node_id = pw.node_id THEN e.to_node_id
                        ELSE e.from_node_id
                    END
                WHERE pw.depth < :max_depth
                  AND NOT (next_node.id = ANY(pw.visited))
            )
            SELECT
                node_id,
                node_title,
                node_type,
                edge_id,
                edge_type_id,
                visited,
                depth
            FROM path_walk
            WHERE node_id = :to_id
            ORDER BY depth
            LIMIT 1
            """
        )

        result = await self.session.execute(
            query,
            {
                "from_id": str(from_id),
                "to_id": str(to_id),
                "max_depth": max_depth,
            },
        )
        row = result.first()

        if row is None:
            return []

        # ``visited`` contains the ordered list of node IDs from source to
        # target.  We now reconstruct the full path with node + edge info.
        visited_ids: list[UUID] = list(row.visited)

        # Fetch all nodes on the path.
        nodes_stmt = select(CorpusNode).where(CorpusNode.id.in_(visited_ids))
        nodes_result = await self.session.execute(nodes_stmt)
        node_map = {n.id: n for n in nodes_result.scalars().all()}

        # Fetch all edges between consecutive nodes on the path.
        path_steps: list[dict] = []
        for i, nid in enumerate(visited_ids):
            node = node_map.get(nid)
            step: dict = {
                "node_id": nid,
                "node_title": node.title if node else None,
                "node_type": node.node_type if node else None,
                "edge_id": None,
                "edge_type_id": None,
            }
            if i > 0:
                prev_id = visited_ids[i - 1]
                edge_stmt = select(Edge).where(
                    ((Edge.from_node_id == prev_id) & (Edge.to_node_id == nid))
                    | ((Edge.from_node_id == nid) & (Edge.to_node_id == prev_id))
                )
                edge_result = await self.session.execute(edge_stmt)
                edge = edge_result.scalar_one_or_none()
                if edge:
                    step["edge_id"] = edge.id
                    step["edge_type_id"] = edge.edge_type_id
            path_steps.append(step)

        return path_steps

    # ------------------------------------------------------------------
    # Full graph -- all nodes and edges, optionally filtered
    # ------------------------------------------------------------------

    async def get_full_graph(
        self,
        node_types: list[str] | None = None,
        edge_types: list[str] | None = None,
    ) -> dict:
        """Return all nodes and edges, optionally filtered by type.

        Returns ``{"nodes": [...], "edges": [...]}``.
        """
        # -- Nodes --
        nodes_stmt = select(CorpusNode)
        if node_types:
            nodes_stmt = nodes_stmt.where(CorpusNode.node_type.in_(node_types))
        nodes_stmt = nodes_stmt.order_by(CorpusNode.created_at.desc())
        nodes_result = await self.session.execute(nodes_stmt)
        nodes = list(nodes_result.scalars().all())

        node_ids = {n.id for n in nodes}

        # -- Edges --
        edges_stmt = select(Edge)
        if edge_types:
            edges_stmt = edges_stmt.where(Edge.edge_type_id.in_(edge_types))
        # Only include edges whose *both* endpoints are in the node set.
        if node_types:
            edges_stmt = edges_stmt.where(
                Edge.from_node_id.in_(node_ids),
                Edge.to_node_id.in_(node_ids),
            )
        edges_result = await self.session.execute(edges_stmt)
        edges = list(edges_result.scalars().all())

        return {"nodes": nodes, "edges": edges}
