"""Repository for Initiatief CRUD and member management."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.initiatief_context import InitiatiefContext
from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.initiatief import (
    Initiatief,
    InitiatiefEenheid,
    InitiatiefMember,
)
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.initiatief import InitiatiefCreate, InitiatiefUpdate


class InitiatiefRepository(BaseRepository[Initiatief]):
    model = Initiatief

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        init_ctx: InitiatiefContext | None = None,
    ) -> list[Initiatief]:
        stmt = select(Initiatief).offset(skip).limit(limit)
        if search:
            escaped = escape_like(search)
            pattern = f"%{escaped}%"
            stmt = stmt.where(Initiatief.naam.ilike(pattern, escape="\\"))
        # Apply visibility filter for non-admins
        if init_ctx and not init_ctx.is_admin and init_ctx.is_authenticated:
            stmt = stmt.where(Initiatief.id.in_(init_ctx.visible_initiatief_ids))
        stmt = stmt.order_by(Initiatief.naam)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_detail(self, id: UUID) -> Initiatief | None:
        stmt = (
            select(Initiatief)
            .where(Initiatief.id == id)
            .options(
                selectinload(Initiatief.members).selectinload(InitiatiefMember.person),
                selectinload(Initiatief.eenheden).selectinload(
                    InitiatiefEenheid.eenheid
                ),
                selectinload(Initiatief.created_by),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, data: InitiatiefCreate, created_by_id: UUID | None = None
    ) -> Initiatief:
        dump = data.model_dump()
        dump["created_by_id"] = created_by_id
        initiatief = Initiatief(**dump)
        self.session.add(initiatief)
        await self.session.flush()

        # Auto-add creator as eigenaar
        if created_by_id:
            member = InitiatiefMember(
                initiatief_id=initiatief.id,
                person_id=created_by_id,
                rol="eigenaar",
            )
            self.session.add(member)
            await self.session.flush()

        await self.session.refresh(initiatief)
        return initiatief

    async def update(self, id: UUID, data: InitiatiefUpdate) -> Initiatief | None:
        initiatief = await self.session.get(Initiatief, id)
        if initiatief is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(initiatief, key, value)
        await self.session.flush()
        await self.session.refresh(initiatief)
        return initiatief

    async def add_member(
        self, initiatief_id: UUID, person_id: UUID, rol: str = "contributor"
    ) -> InitiatiefMember:
        member = InitiatiefMember(
            initiatief_id=initiatief_id,
            person_id=person_id,
            rol=rol,
        )
        self.session.add(member)
        await self.session.flush()
        await self.session.refresh(member, attribute_names=["person"])
        return member

    async def update_member_role(
        self,
        initiatief_id: UUID,
        person_id: UUID,
        rol: str,
    ) -> InitiatiefMember | None:
        stmt = select(InitiatiefMember).where(
            InitiatiefMember.initiatief_id == initiatief_id,
            InitiatiefMember.person_id == person_id,
        )
        result = await self.session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            return None
        member.rol = rol
        await self.session.flush()
        await self.session.refresh(member, attribute_names=["person"])
        return member

    async def remove_member(self, initiatief_id: UUID, person_id: UUID) -> bool:
        stmt = select(InitiatiefMember).where(
            InitiatiefMember.initiatief_id == initiatief_id,
            InitiatiefMember.person_id == person_id,
        )
        result = await self.session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            return False
        await self.session.delete(member)
        await self.session.flush()
        return True

    async def add_eenheid(
        self, initiatief_id: UUID, eenheid_id: UUID
    ) -> InitiatiefEenheid:
        link = InitiatiefEenheid(
            initiatief_id=initiatief_id,
            eenheid_id=eenheid_id,
        )
        self.session.add(link)
        await self.session.flush()
        await self.session.refresh(link, attribute_names=["eenheid"])
        return link

    async def remove_eenheid(self, initiatief_id: UUID, eenheid_id: UUID) -> bool:
        stmt = select(InitiatiefEenheid).where(
            InitiatiefEenheid.initiatief_id == initiatief_id,
            InitiatiefEenheid.eenheid_id == eenheid_id,
        )
        result = await self.session.execute(stmt)
        link = result.scalar_one_or_none()
        if link is None:
            return False
        await self.session.delete(link)
        await self.session.flush()
        return True

    async def is_member(self, initiatief_id: UUID, person_id: UUID) -> bool:
        """Check if person has access to an initiatief (direct or via eenheid)."""
        # Direct membership
        direct = select(InitiatiefMember.person_id).where(
            InitiatiefMember.initiatief_id == initiatief_id,
            InitiatiefMember.person_id == person_id,
        )
        result = await self.session.execute(direct)
        if result.scalar_one_or_none() is not None:
            return True

        # Via organisatie-eenheid
        from datetime import date

        from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

        today = date.today()
        eenheid_stmt = (
            select(InitiatiefEenheid.eenheid_id)
            .join(
                PersonOrganisatieEenheid,
                PersonOrganisatieEenheid.organisatie_eenheid_id
                == InitiatiefEenheid.eenheid_id,
            )
            .where(
                InitiatiefEenheid.initiatief_id == initiatief_id,
                PersonOrganisatieEenheid.person_id == person_id,
                PersonOrganisatieEenheid.start_datum <= today,
                or_(
                    PersonOrganisatieEenheid.eind_datum.is_(None),
                    PersonOrganisatieEenheid.eind_datum >= today,
                ),
            )
        )
        result = await self.session.execute(eenheid_stmt)
        return result.scalar_one_or_none() is not None

    async def count_eigenaren(self, initiatief_id: UUID) -> int:
        """Count the number of eigenaren for an initiatief."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(InitiatiefMember)
            .where(
                InitiatiefMember.initiatief_id == initiatief_id,
                InitiatiefMember.rol == "eigenaar",
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_member_role(self, initiatief_id: UUID, person_id: UUID) -> str | None:
        """Get the direct role of a person in an initiatief, or None."""
        stmt = select(InitiatiefMember.rol).where(
            InitiatiefMember.initiatief_id == initiatief_id,
            InitiatiefMember.person_id == person_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
