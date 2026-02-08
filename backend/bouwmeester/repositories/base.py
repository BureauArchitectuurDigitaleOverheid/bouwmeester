"""Generic base repository with standard CRUD operations."""

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository[T]:
    """Base repository providing get_by_id, update, and delete.

    Subclasses must set the `model` class attribute to the SQLAlchemy model.
    """

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: UUID) -> T | None:
        return await self.session.get(self.model, id)

    async def update(self, id: UUID, data: BaseModel) -> T | None:
        obj = await self.session.get(self.model, id)
        if obj is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id: UUID) -> bool:
        obj = await self.session.get(self.model, id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True
