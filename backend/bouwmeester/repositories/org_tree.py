"""Shared recursive CTE for organisatie-eenheid descendant queries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


async def get_descendant_ids(
    session: AsyncSession,
    root_id: UUID,
    *,
    cte_name: str = "descendants",
) -> list[UUID]:
    """Get all descendant unit IDs (including root) using a recursive CTE."""
    cte = (
        select(OrganisatieEenheid.id)
        .where(OrganisatieEenheid.id == root_id)
        .cte(name=cte_name, recursive=True)
    )
    cte = cte.union_all(
        select(OrganisatieEenheid.id).where(OrganisatieEenheid.parent_id == cte.c.id)
    )
    stmt = select(cte.c.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
