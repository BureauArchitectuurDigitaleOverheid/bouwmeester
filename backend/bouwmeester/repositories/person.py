"""Repository for Person CRUD."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.person import Person
from bouwmeester.schema.person import PersonCreate, PersonUpdate


class PersonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: UUID) -> Person | None:
        return await self.session.get(Person, id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Person]:
        stmt = select(Person).offset(skip).limit(limit).order_by(Person.naam)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: PersonCreate) -> Person:
        person = Person(**data.model_dump())
        self.session.add(person)
        await self.session.flush()
        await self.session.refresh(person)
        return person

    async def update(self, id: UUID, data: PersonUpdate) -> Person | None:
        person = await self.session.get(Person, id)
        if person is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(person, key, value)
        await self.session.flush()
        await self.session.refresh(person)
        return person

    async def delete(self, id: UUID) -> bool:
        person = await self.session.get(Person, id)
        if person is None:
            return False
        await self.session.delete(person)
        await self.session.flush()
        return True

    async def get_by_email(self, email: str) -> Person | None:
        stmt = select(Person).where(Person.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, query: str, limit: int = 10) -> list[Person]:
        stmt = (
            select(Person)
            .where(Person.naam.ilike(f"%{query}%"))
            .order_by(Person.naam)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
