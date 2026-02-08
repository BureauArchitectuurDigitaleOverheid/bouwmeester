"""Repository for EdgeType CRUD."""

from sqlalchemy import select

from bouwmeester.models.edge_type import EdgeType
from bouwmeester.repositories.base import BaseRepository


class EdgeTypeRepository(BaseRepository[EdgeType]):
    model = EdgeType

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

    async def delete(self, id: str) -> bool:  # type: ignore[override]
        edge_type = await self.session.get(EdgeType, id)
        if edge_type is None:
            return False
        await self.session.delete(edge_type)
        await self.session.flush()
        return True
