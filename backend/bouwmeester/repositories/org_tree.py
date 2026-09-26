"""Recursive queries over the organisatie-eenheid tree and memberships.

Two parent sources exist.  ``get_descendant_ids`` walks the temporal
``OrganisatieEenheidParent`` table (active records) and serves reporting
such as task overviews.  Everything that decides access (visibility, rights,
cycle checks) walks ``OrganisatieEenheid.parent_id`` through the functions
below, so a single source decides who may see and do what.

The access queries use ``UNION`` rather than ``UNION ALL``: Postgres then
drops rows it has already produced, so a cycle in the data ends the
recursion instead of looping forever.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.org_parent import OrganisatieEenheidParent
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid


async def get_self_and_ancestor_ids(
    session: AsyncSession, eenheid_id: UUID
) -> set[UUID]:
    """Return *eenheid_id* plus every eenheid above it."""
    cte = (
        select(OrganisatieEenheid.id, OrganisatieEenheid.parent_id)
        .where(OrganisatieEenheid.id == eenheid_id)
        .cte(name="ancestors", recursive=True)
    )
    cte = cte.union(
        select(OrganisatieEenheid.id, OrganisatieEenheid.parent_id).where(
            OrganisatieEenheid.id == cte.c.parent_id
        )
    )
    result = await session.execute(select(cte.c.id))
    return set(result.scalars().all())


async def get_chains(
    session: AsyncSession, eenheid_ids: list[UUID]
) -> dict[UUID, set[UUID]]:
    """``{eenheid: itself plus every eenheid above it}`` for many, in one query.

    The bulk form of :func:`get_self_and_ancestor_ids`.  An id that does not
    exist maps to just itself, like the single form.
    """
    if not eenheid_ids:
        return {}
    cte = (
        select(
            OrganisatieEenheid.id.label("start_id"),
            OrganisatieEenheid.id.label("id"),
            OrganisatieEenheid.parent_id.label("parent_id"),
        )
        .where(OrganisatieEenheid.id.in_(eenheid_ids))
        .cte(name="chains", recursive=True)
    )
    cte = cte.union(
        select(
            cte.c.start_id, OrganisatieEenheid.id, OrganisatieEenheid.parent_id
        ).where(OrganisatieEenheid.id == cte.c.parent_id)
    )
    chains: dict[UUID, set[UUID]] = {eid: {eid} for eid in eenheid_ids}
    for start_id, eid in (
        await session.execute(select(cte.c.start_id, cte.c.id))
    ).all():
        chains[start_id].add(eid)
    return chains


async def get_ancestor_ids(session: AsyncSession, eenheid_ids: list[UUID]) -> set[UUID]:
    """Return every eenheid above any of *eenheid_ids* (not the ids themselves)."""
    if not eenheid_ids:
        return set()
    cte = (
        select(OrganisatieEenheid.parent_id.label("id"))
        .where(
            OrganisatieEenheid.id.in_(eenheid_ids),
            OrganisatieEenheid.parent_id.isnot(None),
        )
        .cte(name="parents", recursive=True)
    )
    cte = cte.union(
        select(OrganisatieEenheid.parent_id).where(
            OrganisatieEenheid.id == cte.c.id,
            OrganisatieEenheid.parent_id.isnot(None),
        )
    )
    result = await session.execute(select(cte.c.id))
    return set(result.scalars().all())


async def get_subtree_ids(session: AsyncSession, eenheid_ids: list[UUID]) -> set[UUID]:
    """Return *eenheid_ids* plus every eenheid below any of them."""
    if not eenheid_ids:
        return set()
    cte = (
        select(OrganisatieEenheid.id)
        .where(OrganisatieEenheid.id.in_(eenheid_ids))
        .cte(name="subtree", recursive=True)
    )
    cte = cte.union(
        select(OrganisatieEenheid.id).where(OrganisatieEenheid.parent_id == cte.c.id)
    )
    result = await session.execute(select(cte.c.id))
    return set(result.scalars().all())


async def get_membership_ids(session: AsyncSession, person_id: UUID) -> list[UUID]:
    """Return the eenheden where *person_id* has an active placement today."""
    today = date.today()
    stmt = select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
        PersonOrganisatieEenheid.person_id == person_id,
        PersonOrganisatieEenheid.start_datum <= today,
        or_(
            PersonOrganisatieEenheid.eind_datum.is_(None),
            PersonOrganisatieEenheid.eind_datum >= today,
        ),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


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
