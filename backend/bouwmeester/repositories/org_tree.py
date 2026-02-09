"""Shared recursive CTE for organisatie-eenheid descendant queries.

Uses the temporal OrganisatieEenheidParent table (active records only)
instead of the legacy parent_id column.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.org_parent import OrganisatieEenheidParent
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
        select(OrganisatieEenheidParent.eenheid_id).where(
            OrganisatieEenheidParent.parent_id == cte.c.id,
            OrganisatieEenheidParent.geldig_tot.is_(None),
        )
    )
    stmt = select(cte.c.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
