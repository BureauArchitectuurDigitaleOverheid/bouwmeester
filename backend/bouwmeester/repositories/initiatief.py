"""Repository for Initiatief CRUD and member management."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.initiatief_context import InitiatiefContext
from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.initiatief import (
    Initiatief,
    InitiatiefEenheid,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.initiatief import (
    EENHEID_ROL_RANK,
    InitiatiefCreate,
    InitiatiefUpdate,
)


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
            rp = ResourcePermission(
                person_id=created_by_id,
                resource_type="initiatief",
                resource_id=initiatief.id,
                rol="eigenaar",
            )
            self.session.add(rp)
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
    ) -> ResourcePermission:
        rp = ResourcePermission(
            person_id=person_id,
            resource_type="initiatief",
            resource_id=initiatief_id,
            rol=rol,
        )
        self.session.add(rp)
        await self.session.flush()
        await self.session.refresh(rp, attribute_names=["person"])
        return rp

    async def update_member_role(
        self,
        initiatief_id: UUID,
        person_id: UUID,
        rol: str,
    ) -> ResourcePermission | None:
        stmt = (
            select(ResourcePermission)
            .where(
                ResourcePermission.resource_type == "initiatief",
                ResourcePermission.resource_id == initiatief_id,
                ResourcePermission.person_id == person_id,
            )
            .options(selectinload(ResourcePermission.person))
        )
        result = await self.session.execute(stmt)
        rp = result.scalar_one_or_none()
        if rp is None:
            return None
        rp.rol = rol
        await self.session.flush()
        await self.session.refresh(rp, attribute_names=["person"])
        return rp

    async def remove_member(self, initiatief_id: UUID, person_id: UUID) -> bool:
        stmt = select(ResourcePermission).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == initiatief_id,
            ResourcePermission.person_id == person_id,
        )
        result = await self.session.execute(stmt)
        rp = result.scalar_one_or_none()
        if rp is None:
            return False
        await self.session.delete(rp)
        await self.session.flush()
        return True

    async def add_eenheid(
        self, initiatief_id: UUID, eenheid_id: UUID, rol: str = "contributor"
    ) -> InitiatiefEenheid:
        link = InitiatiefEenheid(
            initiatief_id=initiatief_id,
            eenheid_id=eenheid_id,
            rol=rol,
        )
        self.session.add(link)
        await self.session.flush()
        await self.session.refresh(link, attribute_names=["eenheid"])
        return link

    async def update_eenheid_rol(
        self, initiatief_id: UUID, eenheid_id: UUID, rol: str
    ) -> InitiatiefEenheid | None:
        stmt = select(InitiatiefEenheid).where(
            InitiatiefEenheid.initiatief_id == initiatief_id,
            InitiatiefEenheid.eenheid_id == eenheid_id,
        )
        result = await self.session.execute(stmt)
        link = result.scalar_one_or_none()
        if link is None:
            return None
        link.rol = rol
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
        """Check if person has access (direct or via eenheid)."""
        direct = select(ResourcePermission.person_id).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == initiatief_id,
            ResourcePermission.person_id == person_id,
        )
        result = await self.session.execute(direct)
        if result.scalar_one_or_none() is not None:
            return True

        from datetime import date

        from bouwmeester.models.person_organisatie import (
            PersonOrganisatieEenheid,
        )

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
        """Count eigenaren for an initiatief."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(ResourcePermission)
            .where(
                ResourcePermission.resource_type == "initiatief",
                ResourcePermission.resource_id == initiatief_id,
                ResourcePermission.rol == "eigenaar",
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_member_role(self, initiatief_id: UUID, person_id: UUID) -> str | None:
        """Get the direct role of a person in an initiatief."""
        stmt = select(ResourcePermission.rol).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == initiatief_id,
            ResourcePermission.person_id == person_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_eenheid_access_level(
        self, initiatief_id: UUID, person_id: UUID
    ) -> str | None:
        """Get the highest access level a person has via eenheid membership.

        Returns the highest-privilege role (eigenaar > contributor > viewer)
        among all eenheden the person belongs to that are linked to this
        initiatief, or None if no eenheid match.
        """
        from datetime import date

        from bouwmeester.models.person_organisatie import (
            PersonOrganisatieEenheid,
        )

        today = date.today()
        stmt = (
            select(InitiatiefEenheid.rol)
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
        result = await self.session.execute(stmt)
        roles = result.scalars().all()
        if not roles:
            return None
        return max(roles, key=lambda r: EENHEID_ROL_RANK.get(r, 0))

    async def list_for_eenheid(self, eenheid_id: UUID) -> list[InitiatiefEenheid]:
        """List initiatieven linked to an eenheid."""
        stmt = (
            select(InitiatiefEenheid)
            .where(InitiatiefEenheid.eenheid_id == eenheid_id)
            .options(selectinload(InitiatiefEenheid.initiatief))
            .order_by(InitiatiefEenheid.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
