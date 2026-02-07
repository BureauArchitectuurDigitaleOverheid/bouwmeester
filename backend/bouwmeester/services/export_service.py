"""Service layer for export operations."""

import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def export_nodes_csv(self, node_type: str | None = None) -> str:
        """Generate CSV string of nodes."""
        stmt = select(CorpusNode).order_by(CorpusNode.created_at.desc())
        if node_type is not None:
            stmt = stmt.where(CorpusNode.node_type == node_type)
        result = await self.session.execute(stmt)
        nodes = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id", "title", "node_type", "description",
                "status", "created_at", "updated_at",
            ]
        )
        for node in nodes:
            writer.writerow(
                [
                    str(node.id),
                    node.title,
                    node.node_type,
                    node.description or "",
                    node.status,
                    node.created_at.isoformat() if node.created_at else "",
                    node.updated_at.isoformat() if node.updated_at else "",
                ]
            )
        return output.getvalue()

    async def export_edges_csv(self) -> str:
        """Generate CSV string of edges."""
        from sqlalchemy.orm import selectinload

        stmt = (
            select(Edge)
            .options(selectinload(Edge.from_node), selectinload(Edge.to_node))
            .order_by(Edge.created_at.desc())
        )
        result = await self.session.execute(stmt)
        edges = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "from_node_id",
                "from_node_title",
                "to_node_id",
                "to_node_title",
                "edge_type_id",
                "weight",
                "description",
                "created_at",
            ]
        )
        for edge in edges:
            writer.writerow(
                [
                    str(edge.id),
                    str(edge.from_node_id),
                    edge.from_node.title if edge.from_node else "",
                    str(edge.to_node_id),
                    edge.to_node.title if edge.to_node else "",
                    edge.edge_type_id,
                    edge.weight,
                    edge.description or "",
                    edge.created_at.isoformat() if edge.created_at else "",
                ]
            )
        return output.getvalue()

    async def export_corpus_json(self) -> dict:
        """Full corpus as JSON with nodes, edges, edge_types."""
        # Nodes
        nodes_stmt = select(CorpusNode).order_by(CorpusNode.created_at.desc())
        nodes_result = await self.session.execute(nodes_stmt)
        nodes = nodes_result.scalars().all()

        # Edges
        edges_stmt = select(Edge).order_by(Edge.created_at.desc())
        edges_result = await self.session.execute(edges_stmt)
        edges = edges_result.scalars().all()

        # Edge Types
        edge_types_stmt = select(EdgeType).order_by(EdgeType.id)
        edge_types_result = await self.session.execute(edge_types_stmt)
        edge_types = edge_types_result.scalars().all()

        return {
            "nodes": [
                {
                    "id": str(n.id),
                    "title": n.title,
                    "node_type": n.node_type,
                    "description": n.description,
                    "status": n.status,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                    "updated_at": n.updated_at.isoformat() if n.updated_at else None,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "from_node_id": str(e.from_node_id),
                    "to_node_id": str(e.to_node_id),
                    "edge_type_id": e.edge_type_id,
                    "weight": e.weight,
                    "description": e.description,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in edges
            ],
            "edge_types": [
                {
                    "id": et.id,
                    "label_nl": et.label_nl,
                    "label_en": et.label_en,
                    "description": et.description,
                    "is_custom": et.is_custom,
                }
                for et in edge_types
            ],
        }
