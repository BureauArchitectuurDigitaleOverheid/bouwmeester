"""Repository for OrganisatieEenheid CRUD and tree queries."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidUpdate,
)


class OrganisatieEenheidRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: UUID) -> OrganisatieEenheid | None:
        return await self.session.get(OrganisatieEenheid, id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 500,
    ) -> list[OrganisatieEenheid]:
        stmt = (
            select(OrganisatieEenheid)
            .offset(skip)
            .limit(limit)
            .order_by(OrganisatieEenheid.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_parent(
        self,
        parent_id: UUID | None,
    ) -> list[OrganisatieEenheid]:
        if parent_id is None:
            stmt = select(OrganisatieEenheid).where(
                OrganisatieEenheid.parent_id.is_(None)
            )
        else:
            stmt = select(OrganisatieEenheid).where(
                OrganisatieEenheid.parent_id == parent_id
            )
        stmt = stmt.order_by(OrganisatieEenheid.naam)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: OrganisatieEenheidCreate) -> OrganisatieEenheid:
        eenheid = OrganisatieEenheid(**data.model_dump())
        self.session.add(eenheid)
        await self.session.flush()
        await self.session.refresh(eenheid)
        return eenheid

    async def update(
        self, id: UUID, data: OrganisatieEenheidUpdate
    ) -> OrganisatieEenheid | None:
        eenheid = await self.session.get(OrganisatieEenheid, id)
        if eenheid is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(eenheid, key, value)
        await self.session.flush()
        await self.session.refresh(eenheid)
        return eenheid

    async def delete(self, id: UUID) -> bool:
        eenheid = await self.session.get(OrganisatieEenheid, id)
        if eenheid is None:
            return False
        await self.session.delete(eenheid)
        await self.session.flush()
        return True

    async def has_children(self, id: UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(OrganisatieEenheid)
            .where(OrganisatieEenheid.parent_id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def has_personen(self, id: UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(Person)
            .where(Person.organisatie_eenheid_id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def get_personen(self, id: UUID) -> list[Person]:
        stmt = (
            select(Person)
            .where(Person.organisatie_eenheid_id == id)
            .order_by(Person.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_personen(self, id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Person)
            .where(Person.organisatie_eenheid_id == id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_descendant_ids(self, root_id: UUID) -> list[UUID]:
        """Get all descendant unit IDs (including root) using a recursive CTE."""
        cte = (
            select(OrganisatieEenheid.id)
            .where(OrganisatieEenheid.id == root_id)
            .cte(name="descendants", recursive=True)
        )
        cte = cte.union_all(
            select(OrganisatieEenheid.id).where(
                OrganisatieEenheid.parent_id == cte.c.id
            )
        )
        stmt = select(cte.c.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_units_by_ids(self, unit_ids: list[UUID]) -> list[OrganisatieEenheid]:
        """Fetch all units for given IDs, with manager eager-loaded."""
        if not unit_ids:
            return []
        stmt = (
            select(OrganisatieEenheid)
            .options(joinedload(OrganisatieEenheid.manager))
            .where(OrganisatieEenheid.id.in_(unit_ids))
            .order_by(OrganisatieEenheid.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def search(self, query: str, limit: int = 10) -> list[OrganisatieEenheid]:
        stmt = (
            select(OrganisatieEenheid)
            .where(OrganisatieEenheid.naam.ilike(f"%{query}%"))
            .order_by(OrganisatieEenheid.naam)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_personen_for_units(self, unit_ids: list[UUID]) -> list[Person]:
        """Fetch all people for a list of unit IDs in one query."""
        if not unit_ids:
            return []
        stmt = (
            select(Person)
            .where(Person.organisatie_eenheid_id.in_(unit_ids))
            .order_by(Person.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
