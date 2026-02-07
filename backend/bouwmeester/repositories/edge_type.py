"""Repository for EdgeType CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.edge_type import EdgeType
from bouwmeester.schema.edge_type import EdgeTypeCreate


class EdgeTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: str) -> EdgeType | None:
        return await self.session.get(EdgeType, id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[EdgeType]:
        stmt = select(EdgeType).offset(skip).limit(limit).order_by(EdgeType.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: EdgeTypeCreate) -> EdgeType:
        edge_type = EdgeType(**data.model_dump())
        self.session.add(edge_type)
        await self.session.flush()
        await self.session.refresh(edge_type)
        return edge_type

    async def delete(self, id: str) -> bool:
        edge_type = await self.session.get(EdgeType, id)
        if edge_type is None:
            return False
        await self.session.delete(edge_type)
        await self.session.flush()
        return True
