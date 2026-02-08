"""Repository for OrganisatieEenheid CRUD and tree queries."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
)


class OrganisatieEenheidRepository(BaseRepository[OrganisatieEenheid]):
    model = OrganisatieEenheid

    async def get(self, id: UUID) -> OrganisatieEenheid | None:
        return await self.get_by_id(id)

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
            .select_from(PersonOrganisatieEenheid)
            .where(
                PersonOrganisatieEenheid.organisatie_eenheid_id == id,
                PersonOrganisatieEenheid.eind_datum.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def get_personen(self, id: UUID) -> list[Person]:
        stmt = (
            select(Person)
            .join(PersonOrganisatieEenheid)
            .where(
                PersonOrganisatieEenheid.organisatie_eenheid_id == id,
                PersonOrganisatieEenheid.eind_datum.is_(None),
            )
            .order_by(Person.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_personen(self, id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(PersonOrganisatieEenheid)
            .where(
                PersonOrganisatieEenheid.organisatie_eenheid_id == id,
                PersonOrganisatieEenheid.eind_datum.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_descendant_ids(self, root_id: UUID) -> list[UUID]:
        """Get all descendant unit IDs (including root) using a recursive CTE."""
        from bouwmeester.repositories.org_tree import get_descendant_ids

        return await get_descendant_ids(self.session, root_id)

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

    async def get_by_manager(self, person_id: UUID) -> list[OrganisatieEenheid]:
        """Get all eenheden where this person is manager."""
        stmt = (
            select(OrganisatieEenheid)
            .where(OrganisatieEenheid.manager_id == person_id)
            .order_by(OrganisatieEenheid.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_personen_for_units(
        self, unit_ids: list[UUID]
    ) -> list[tuple[Person, UUID]]:
        """Fetch all active (person, unit_id) pairs for a list of unit IDs."""
        if not unit_ids:
            return []
        stmt = (
            select(Person, PersonOrganisatieEenheid.organisatie_eenheid_id)
            .join(PersonOrganisatieEenheid)
            .where(
                PersonOrganisatieEenheid.organisatie_eenheid_id.in_(unit_ids),
                PersonOrganisatieEenheid.eind_datum.is_(None),
            )
            .order_by(Person.naam)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
