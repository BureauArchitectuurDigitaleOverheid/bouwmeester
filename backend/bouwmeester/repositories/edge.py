"""Repository for Edge CRUD."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.edge import Edge
from bouwmeester.schema.edge import EdgeCreate, EdgeUpdate


class EdgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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

    async def create(self, data: EdgeCreate) -> Edge:
        edge = Edge(**data.model_dump())
        self.session.add(edge)
        await self.session.flush()
        await self.session.refresh(edge)
        return edge

    async def update(self, id: UUID, data: EdgeUpdate) -> Edge | None:
        edge = await self.session.get(Edge, id)
        if edge is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(edge, key, value)
        await self.session.flush()
        await self.session.refresh(edge)
        return edge

    async def delete(self, id: UUID) -> bool:
        edge = await self.session.get(Edge, id)
        if edge is None:
            return False
        await self.session.delete(edge)
        await self.session.flush()
        return True
