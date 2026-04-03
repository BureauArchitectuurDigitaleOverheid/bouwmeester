"""Repository for ExterneOrganisatie CRUD."""

from sqlalchemy import select

from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.externe_organisatie import ExterneOrganisatie
from bouwmeester.repositories.base import BaseRepository


class ExterneOrganisatieRepository(BaseRepository[ExterneOrganisatie]):
    model = ExterneOrganisatie

    async def get_or_create_by_name(self, name: str) -> ExterneOrganisatie:
        """Find ExterneOrganisatie by afkorting or naam, or create it.

        Prefers an exact afkorting match over a naam match to avoid
        ambiguity when multiple orgs share a name fragment.
        """
        # Try afkorting first (most specific)
        stmt = select(ExterneOrganisatie).where(
            ExterneOrganisatie.afkorting.ilike(name)
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        if existing:
            return existing

        # Fall back to naam
        stmt = select(ExterneOrganisatie).where(ExterneOrganisatie.naam.ilike(name))
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        if existing:
            return existing

        new_org = ExterneOrganisatie(
            naam=name,
            afkorting=name,
            type="uitvoeringsorganisatie",
        )
        self.session.add(new_org)
        await self.session.flush()
        return new_org

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        type: str | None = None,
        search: str | None = None,
    ) -> list[ExterneOrganisatie]:
        stmt = select(ExterneOrganisatie).offset(skip).limit(limit)
        if type is not None:
            stmt = stmt.where(ExterneOrganisatie.type == type)
        if search:
            escaped = escape_like(search)
            pattern = f"%{escaped}%"
            stmt = stmt.where(
                ExterneOrganisatie.naam.ilike(pattern, escape="\\")
                | ExterneOrganisatie.afkorting.ilike(pattern, escape="\\")
            )
        stmt = stmt.order_by(ExterneOrganisatie.naam)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
