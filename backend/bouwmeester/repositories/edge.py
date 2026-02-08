"""Repository for Edge CRUD."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bouwmeester.models.edge import Edge
from bouwmeester.repositories.base import BaseRepository


class EdgeRepository(BaseRepository[Edge]):
    model = Edge

    async def get(self, id: UUID) -> Edge | None:
        stmt = (
            select(Edge)
            .where(Edge.id == id)
            .options(
                selectinload(Edge.from_node),
                selectinload(Edge.to_node),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        from_node_id: UUID | None = None,
        to_node_id: UUID | None = None,
        node_id: UUID | None = None,
        edge_type_id: str | None = None,
    ) -> list[Edge]:
        from sqlalchemy import or_

        stmt = (
            select(Edge)
            .options(selectinload(Edge.from_node), selectinload(Edge.to_node))
            .offset(skip)
            .limit(limit)
        )
        if node_id is not None:
            stmt = stmt.where(
                or_(Edge.from_node_id == node_id, Edge.to_node_id == node_id)
            )
        if from_node_id is not None:
            stmt = stmt.where(Edge.from_node_id == from_node_id)
        if to_node_id is not None:
            stmt = stmt.where(Edge.to_node_id == to_node_id)
        if edge_type_id is not None:
            stmt = stmt.where(Edge.edge_type_id == edge_type_id)
        stmt = stmt.order_by(Edge.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

