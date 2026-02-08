"""Repository for Person CRUD."""

from uuid import UUID

from sqlalchemy import select

from bouwmeester.models.person import Person
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.person import PersonCreate


class PersonRepository(BaseRepository[Person]):
    model = Person

    async def get(self, id: UUID) -> Person | None:
        return await self.get_by_id(id)

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
