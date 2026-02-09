"""Repository for OrganisatieEenheid CRUD and tree queries.

Overrides BaseRepository.create() and update() to manage temporal records
(naam, parent, manager) alongside dual-written legacy columns.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from bouwmeester.models.org_manager import OrganisatieEenheidManager
from bouwmeester.models.org_naam import OrganisatieEenheidNaam
from bouwmeester.models.org_parent import OrganisatieEenheidParent
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.organisatie_eenheid import (
    OrganisatieEenheidCreate,
    OrganisatieEenheidUpdate,
)


class OrganisatieEenheidRepository(BaseRepository[OrganisatieEenheid]):
    model = OrganisatieEenheid

    # ------------------------------------------------------------------
    # Create / Update (temporal-aware overrides)
    # ------------------------------------------------------------------

    async def create(self, data: OrganisatieEenheidCreate) -> OrganisatieEenheid:
        effective = data.geldig_van or date.today()
        eenheid = OrganisatieEenheid(
            naam=data.naam,
            type=data.type,
            parent_id=data.parent_id,
            manager_id=data.manager_id,
            beschrijving=data.beschrijving,
            geldig_van=effective,
        )
        self.session.add(eenheid)
        await self.session.flush()

        # Temporal name record (always)
        self.session.add(
            OrganisatieEenheidNaam(
                eenheid_id=eenheid.id,
                naam=data.naam,
                geldig_van=effective,
            )
        )
        if data.parent_id is not None:
            self.session.add(
                OrganisatieEenheidParent(
                    eenheid_id=eenheid.id,
                    parent_id=data.parent_id,
                    geldig_van=effective,
                )
            )
        if data.manager_id is not None:
            self.session.add(
                OrganisatieEenheidManager(
                    eenheid_id=eenheid.id,
                    manager_id=data.manager_id,
                    geldig_van=effective,
                )
            )

        await self.session.flush()
        await self.session.refresh(eenheid)
        return eenheid

    async def update(
        self,
        id: UUID,
        data: OrganisatieEenheidUpdate,
    ) -> OrganisatieEenheid | None:
        eenheid = await self.session.get(OrganisatieEenheid, id)
        if eenheid is None:
            return None

        changes = data.model_dump(exclude_unset=True)
        effective = changes.pop("wijzig_datum", None) or date.today()

        # Dissolution: close all active temporal records
        if "geldig_tot" in changes:
            end = changes["geldig_tot"]
            eenheid.geldig_tot = end
            await self._close_all_active(eenheid.id, end)

        # Name change
        if "naam" in changes and changes["naam"] != eenheid.naam:
            await self._rotate_naam(eenheid.id, changes["naam"], effective)
            eenheid.naam = changes["naam"]

        # Parent change
        if "parent_id" in changes and changes["parent_id"] != eenheid.parent_id:
            await self._rotate_parent(
                eenheid.id,
                changes["parent_id"],
                effective,
            )
            eenheid.parent_id = changes["parent_id"]

        # Manager change
        if "manager_id" in changes and changes["manager_id"] != eenheid.manager_id:
            await self._rotate_manager(
                eenheid.id,
                changes["manager_id"],
                effective,
            )
            eenheid.manager_id = changes["manager_id"]

        # Simple field updates
        for key in ("type", "beschrijving"):
            if key in changes:
                setattr(eenheid, key, changes[key])

        await self.session.flush()
        await self.session.refresh(eenheid)
        return eenheid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(self, id: UUID) -> OrganisatieEenheid | None:
        return await self.get_by_id(id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 500,
        *,
        active_only: bool = True,
    ) -> list[OrganisatieEenheid]:
        stmt = select(OrganisatieEenheid).offset(skip).limit(limit)
        if active_only:
            stmt = stmt.where(OrganisatieEenheid.geldig_tot.is_(None))
        stmt = stmt.order_by(OrganisatieEenheid.naam)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_parent(
        self,
        parent_id: UUID | None,
    ) -> list[OrganisatieEenheid]:
        if parent_id is None:
            # Root units: those without an active parent record
            subq = select(OrganisatieEenheidParent.eenheid_id).where(
                OrganisatieEenheidParent.geldig_tot.is_(None),
            )
            stmt = select(OrganisatieEenheid).where(
                OrganisatieEenheid.id.notin_(subq),
                OrganisatieEenheid.geldig_tot.is_(None),
            )
        else:
            stmt = (
                select(OrganisatieEenheid)
                .join(
                    OrganisatieEenheidParent,
                    OrganisatieEenheidParent.eenheid_id == OrganisatieEenheid.id,
                )
                .where(
                    OrganisatieEenheidParent.parent_id == parent_id,
                    OrganisatieEenheidParent.geldig_tot.is_(None),
                )
            )
        stmt = stmt.order_by(OrganisatieEenheid.naam)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def has_children(self, id: UUID) -> bool:
        stmt = (
            select(func.count())
            .select_from(OrganisatieEenheidParent)
            .where(
                OrganisatieEenheidParent.parent_id == id,
                OrganisatieEenheidParent.geldig_tot.is_(None),
            )
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
        from bouwmeester.repositories.org_tree import get_descendant_ids

        return await get_descendant_ids(self.session, root_id)

    async def get_units_by_ids(
        self,
        unit_ids: list[UUID],
    ) -> list[OrganisatieEenheid]:
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

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[OrganisatieEenheid]:
        """Search across all names (historical + current), active units only."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = (
            select(OrganisatieEenheid)
            .join(
                OrganisatieEenheidNaam,
                OrganisatieEenheidNaam.eenheid_id == OrganisatieEenheid.id,
            )
            .where(
                OrganisatieEenheidNaam.naam.ilike(f"%{escaped}%"),
                OrganisatieEenheid.geldig_tot.is_(None),
            )
            .distinct()
            .order_by(OrganisatieEenheid.naam)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_manager(
        self,
        person_id: UUID,
    ) -> list[OrganisatieEenheid]:
        """Get all active eenheden where this person is current manager."""
        stmt = (
            select(OrganisatieEenheid)
            .join(
                OrganisatieEenheidManager,
                OrganisatieEenheidManager.eenheid_id == OrganisatieEenheid.id,
            )
            .where(
                OrganisatieEenheidManager.manager_id == person_id,
                OrganisatieEenheidManager.geldig_tot.is_(None),
            )
            .order_by(OrganisatieEenheid.naam)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_personen_for_units(
        self,
        unit_ids: list[UUID],
    ) -> list[tuple[Person, UUID]]:
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

    # ------------------------------------------------------------------
    # History queries
    # ------------------------------------------------------------------

    async def get_naam_history(
        self,
        eenheid_id: UUID,
    ) -> list[OrganisatieEenheidNaam]:
        stmt = (
            select(OrganisatieEenheidNaam)
            .where(OrganisatieEenheidNaam.eenheid_id == eenheid_id)
            .order_by(
                OrganisatieEenheidNaam.geldig_van.desc(),
                OrganisatieEenheidNaam.geldig_tot.asc().nulls_first(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_parent_history(
        self,
        eenheid_id: UUID,
    ) -> list[OrganisatieEenheidParent]:
        stmt = (
            select(OrganisatieEenheidParent)
            .where(OrganisatieEenheidParent.eenheid_id == eenheid_id)
            .order_by(
                OrganisatieEenheidParent.geldig_van.desc(),
                OrganisatieEenheidParent.geldig_tot.asc().nulls_first(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_manager_history(
        self,
        eenheid_id: UUID,
    ) -> list[OrganisatieEenheidManager]:
        stmt = (
            select(OrganisatieEenheidManager)
            .where(OrganisatieEenheidManager.eenheid_id == eenheid_id)
            .order_by(
                OrganisatieEenheidManager.geldig_van.desc(),
                OrganisatieEenheidManager.geldig_tot.asc().nulls_first(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Private temporal helpers
    # ------------------------------------------------------------------

    async def _rotate_naam(
        self,
        eenheid_id: UUID,
        new_naam: str,
        effective: date,
    ) -> None:
        stmt = select(OrganisatieEenheidNaam).where(
            OrganisatieEenheidNaam.eenheid_id == eenheid_id,
            OrganisatieEenheidNaam.geldig_tot.is_(None),
        )
        result = await self.session.execute(stmt)
        active = result.scalar_one_or_none()
        if active:
            active.geldig_tot = effective
        self.session.add(
            OrganisatieEenheidNaam(
                eenheid_id=eenheid_id,
                naam=new_naam,
                geldig_van=effective,
            )
        )

    async def _rotate_parent(
        self,
        eenheid_id: UUID,
        new_parent_id: UUID | None,
        effective: date,
    ) -> None:
        stmt = select(OrganisatieEenheidParent).where(
            OrganisatieEenheidParent.eenheid_id == eenheid_id,
            OrganisatieEenheidParent.geldig_tot.is_(None),
        )
        result = await self.session.execute(stmt)
        active = result.scalar_one_or_none()
        if active:
            active.geldig_tot = effective
        if new_parent_id is not None:
            self.session.add(
                OrganisatieEenheidParent(
                    eenheid_id=eenheid_id,
                    parent_id=new_parent_id,
                    geldig_van=effective,
                )
            )

    async def _rotate_manager(
        self,
        eenheid_id: UUID,
        new_manager_id: UUID | None,
        effective: date,
    ) -> None:
        stmt = select(OrganisatieEenheidManager).where(
            OrganisatieEenheidManager.eenheid_id == eenheid_id,
            OrganisatieEenheidManager.geldig_tot.is_(None),
        )
        result = await self.session.execute(stmt)
        active = result.scalar_one_or_none()
        if active:
            active.geldig_tot = effective
        if new_manager_id is not None:
            self.session.add(
                OrganisatieEenheidManager(
                    eenheid_id=eenheid_id,
                    manager_id=new_manager_id,
                    geldig_van=effective,
                )
            )

    async def _close_all_active(
        self,
        eenheid_id: UUID,
        end_date: date,
    ) -> None:
        """Close all active temporal records for a dissolved unit."""
        for model_cls in (
            OrganisatieEenheidNaam,
            OrganisatieEenheidParent,
            OrganisatieEenheidManager,
        ):
            stmt = select(model_cls).where(
                model_cls.eenheid_id == eenheid_id,
                model_cls.geldig_tot.is_(None),
            )
            result = await self.session.execute(stmt)
            for record in result.scalars().all():
                record.geldig_tot = end_date
