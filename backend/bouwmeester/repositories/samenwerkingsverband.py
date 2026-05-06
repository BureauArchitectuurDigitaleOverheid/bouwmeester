"""Repository for Samenwerkingsverband CRUD and lidmaatschap management."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.persoon_samenwerkingsverband import (
    PersoonSamenwerkingsverband,
)
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.samenwerkingsverband import (
    SamenwerkingsverbandCreate,
    SamenwerkingsverbandUpdate,
)


class SamenwerkingsverbandRepository(BaseRepository[Samenwerkingsverband]):
    model = Samenwerkingsverband

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 1000,
        search: str | None = None,
        type_filter: str | None = None,
        actief: bool | None = None,
    ) -> list[tuple[Samenwerkingsverband, int]]:
        """Return (verband, aantal_actieve_leden) tuples."""
        today = date.today()
        ledental_subq = (
            select(func.count(PersoonSamenwerkingsverband.id))
            .where(
                PersoonSamenwerkingsverband.samenwerkingsverband_id
                == Samenwerkingsverband.id,
                PersoonSamenwerkingsverband.start_datum <= today,
                or_(
                    PersoonSamenwerkingsverband.eind_datum.is_(None),
                    PersoonSamenwerkingsverband.eind_datum >= today,
                ),
            )
            .correlate(Samenwerkingsverband)
            .scalar_subquery()
        )

        stmt = select(Samenwerkingsverband, ledental_subq.label("aantal_leden"))
        if search:
            pattern = f"%{escape_like(search)}%"
            stmt = stmt.where(Samenwerkingsverband.naam.ilike(pattern, escape="\\"))
        if type_filter:
            stmt = stmt.where(Samenwerkingsverband.type == type_filter)
        if actief is True:
            stmt = stmt.where(
                or_(
                    Samenwerkingsverband.eind_datum.is_(None),
                    Samenwerkingsverband.eind_datum >= today,
                )
            )
        elif actief is False:
            stmt = stmt.where(
                Samenwerkingsverband.eind_datum.is_not(None),
                Samenwerkingsverband.eind_datum < today,
            )

        stmt = stmt.order_by(Samenwerkingsverband.naam).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return [(row[0], row[1] or 0) for row in result.all()]

    async def get(self, id: UUID) -> Samenwerkingsverband | None:
        stmt = (
            select(Samenwerkingsverband)
            .where(Samenwerkingsverband.id == id)
            .options(selectinload(Samenwerkingsverband.created_by))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active_members(self, id: UUID) -> int:
        today = date.today()
        stmt = select(func.count(PersoonSamenwerkingsverband.id)).where(
            PersoonSamenwerkingsverband.samenwerkingsverband_id == id,
            PersoonSamenwerkingsverband.start_datum <= today,
            or_(
                PersoonSamenwerkingsverband.eind_datum.is_(None),
                PersoonSamenwerkingsverband.eind_datum >= today,
            ),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_members(
        self, id: UUID, actief: bool = True
    ) -> list[PersoonSamenwerkingsverband]:
        today = date.today()
        stmt = (
            select(PersoonSamenwerkingsverband)
            .where(PersoonSamenwerkingsverband.samenwerkingsverband_id == id)
            .options(selectinload(PersoonSamenwerkingsverband.person))
            .order_by(PersoonSamenwerkingsverband.start_datum.desc())
        )
        if actief:
            stmt = stmt.where(
                PersoonSamenwerkingsverband.start_datum <= today,
                or_(
                    PersoonSamenwerkingsverband.eind_datum.is_(None),
                    PersoonSamenwerkingsverband.eind_datum >= today,
                ),
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_person(
        self, person_id: UUID, actief: bool = True
    ) -> list[PersoonSamenwerkingsverband]:
        today = date.today()
        stmt = (
            select(PersoonSamenwerkingsverband)
            .where(PersoonSamenwerkingsverband.person_id == person_id)
            .options(
                selectinload(PersoonSamenwerkingsverband.samenwerkingsverband),
            )
            .order_by(PersoonSamenwerkingsverband.start_datum.desc())
        )
        if actief:
            stmt = stmt.where(
                PersoonSamenwerkingsverband.start_datum <= today,
                or_(
                    PersoonSamenwerkingsverband.eind_datum.is_(None),
                    PersoonSamenwerkingsverband.eind_datum >= today,
                ),
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        data: SamenwerkingsverbandCreate,
        created_by_id: UUID | None = None,
    ) -> Samenwerkingsverband:
        obj = Samenwerkingsverband(**data.model_dump(), created_by_id=created_by_id)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(
        self, id: UUID, data: SamenwerkingsverbandUpdate
    ) -> Samenwerkingsverband | None:
        obj = await self.session.get(Samenwerkingsverband, id)
        if obj is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj
