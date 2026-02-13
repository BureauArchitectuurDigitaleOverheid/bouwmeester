"""Repository for Person CRUD."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.repositories.base import BaseRepository


class PersonRepository(BaseRepository[Person]):
    model = Person

    def _eager_options(self):
        return [selectinload(Person.emails), selectinload(Person.phones)]

    async def get(self, id: UUID) -> Person | None:
        stmt = select(Person).where(Person.id == id).options(*self._eager_options())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Person]:
        stmt = (
            select(Person)
            .options(*self._eager_options())
            .offset(skip)
            .limit(limit)
            .order_by(Person.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_email(self, email: str) -> Person | None:
        stmt = (
            select(Person)
            .join(PersonEmail)
            .where(PersonEmail.email == email)
            .options(*self._eager_options())
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, query: str, limit: int = 10) -> list[Person]:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = (
            select(Person)
            .options(*self._eager_options())
            .where(Person.naam.ilike(f"%{escaped}%"))
            .order_by(Person.naam)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
