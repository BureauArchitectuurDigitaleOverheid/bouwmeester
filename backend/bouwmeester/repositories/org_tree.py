"""Recursive queries over the organisatie-eenheid tree and memberships.

Membership (who counts as placed in an eenheid for access) is defined once,
in ``membership_ids_select``: an active placement with a trusted bron.

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

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.lead import Lead
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.org_parent import OrganisatieEenheidParent
from bouwmeester.models.organisatie_eenheid import (
    INTERNAL_EENHEID_TYPES,
    OrganisatieEenheid,
)
from bouwmeester.models.person_organisatie import (
    TRUSTED_PLACEMENT_BRONNEN,
    PersonOrganisatieEenheid,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.task import Task


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


async def touches_organisation(session: AsyncSession, eenheid_id: UUID) -> bool:
    """True if *eenheid_id* or an eenheid above it is internal.

    Members see their eenheid and everything above it, so an external
    organisation that hangs below a ministerie reaches inside: its members
    and its creation are matters of the internal organisation.
    """
    cte = (
        select(
            OrganisatieEenheid.id, OrganisatieEenheid.parent_id, OrganisatieEenheid.type
        )
        .where(OrganisatieEenheid.id == eenheid_id)
        .cte(name="chain_types", recursive=True)
    )
    cte = cte.union(
        select(
            OrganisatieEenheid.id, OrganisatieEenheid.parent_id, OrganisatieEenheid.type
        ).where(OrganisatieEenheid.id == cte.c.parent_id)
    )
    hit = await session.scalar(
        select(cte.c.id).where(cte.c.type.in_(INTERNAL_EENHEID_TYPES)).limit(1)
    )
    return hit is not None


async def get_organisation_ids(session: AsyncSession) -> set[UUID]:
    """Every eenheid that touches the organisation: internal ones and below them.

    The bulk form of :func:`touches_organisation`.
    """
    internal = (
        await session.scalars(
            select(OrganisatieEenheid.id).where(
                OrganisatieEenheid.type.in_(INTERNAL_EENHEID_TYPES)
            )
        )
    ).all()
    return await get_subtree_ids(session, list(internal))


def placement_not_ended(today: date | None = None):
    """SQL: the placement has not ended (it may still have to start)."""
    today = today or date.today()
    return or_(
        PersonOrganisatieEenheid.eind_datum.is_(None),
        PersonOrganisatieEenheid.eind_datum >= today,
    )


def placement_active(today: date | None = None):
    """SQL: the placement holds today."""
    today = today or date.today()
    return and_(
        PersonOrganisatieEenheid.start_datum <= today, placement_not_ended(today)
    )


def placement_trusted():
    """SQL: the placement gives access (``TRUSTED_PLACEMENT_BRONNEN``).

    Every other placement is informational: it shows who works where, but
    gives neither visibility nor the grants held by the eenheid.
    """
    return PersonOrganisatieEenheid.bron.in_(TRUSTED_PLACEMENT_BRONNEN)


def membership_ids_select(person_id: UUID) -> Select:
    """SELECT the eenheden *person_id* is a member of today, for access.

    The one definition of membership: an active, trusted placement.
    Visibility (own eenheden, read up the line), the implicit viewer role,
    edit shares and resource roles held by an eenheid all resolve through
    it; use it as a subquery where a join is needed.
    """
    return select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
        PersonOrganisatieEenheid.person_id == person_id,
        placement_active(),
        placement_trusted(),
    )


async def get_membership_ids(session: AsyncSession, person_id: UUID) -> list[UUID]:
    """The eenheden *person_id* is a member of today (see ``membership_ids_select``).

    Ordered longest-running first: earliest ``start_datum`` of a trusted,
    active placement, then eenheid naam, then id.  Whoever needs "the"
    own eenheid of someone with several placements takes the first one,
    so REST and chat pick the same eenheid.
    """
    eenheid_id = PersonOrganisatieEenheid.organisatie_eenheid_id
    stmt = (
        membership_ids_select(person_id)
        .join(OrganisatieEenheid, OrganisatieEenheid.id == eenheid_id)
        .group_by(eenheid_id, OrganisatieEenheid.naam)
        .order_by(
            func.min(PersonOrganisatieEenheid.start_datum),
            OrganisatieEenheid.naam,
            eenheid_id,
        )
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


def _reference_queries(
    eenheid_id: UUID, *, structure: bool
) -> list[tuple[str, Select]]:
    """Labelled count queries for what refers to *eenheid_id*."""

    def count(model, *where) -> Select:
        return select(func.count()).select_from(model).where(*where)

    queries = [
        ("nodes", count(CorpusNode, CorpusNode.organisatie_eenheid_id == eenheid_id)),
        ("leads", count(Lead, Lead.organisatie_eenheid_id == eenheid_id)),
        ("taken", count(Task, Task.organisatie_eenheid_id == eenheid_id)),
        (
            "opdrachten",
            count(
                Opdracht,
                or_(
                    Opdracht.opdrachtgever_id == eenheid_id,
                    Opdracht.opdrachtnemer_eenheid_id == eenheid_id,
                ),
            ),
        ),
        (
            "toegangsrechten (bijvoorbeeld op initiatieven)",
            count(
                ResourcePermission,
                ResourcePermission.organisatie_eenheid_id == eenheid_id,
            ),
        ),
        (
            "gedeelde toegang",
            count(
                SharedAccess,
                or_(
                    SharedAccess.source_eenheid_id == eenheid_id,
                    SharedAccess.target_eenheid_id == eenheid_id,
                ),
            ),
        ),
    ]
    if structure:
        queries[:0] = [
            (
                "subeenheden",
                count(
                    OrganisatieEenheid,
                    or_(
                        OrganisatieEenheid.parent_id == eenheid_id,
                        OrganisatieEenheid.id.in_(
                            select(OrganisatieEenheidParent.eenheid_id).where(
                                OrganisatieEenheidParent.parent_id == eenheid_id,
                                OrganisatieEenheidParent.geldig_tot.is_(None),
                            )
                        ),
                    ),
                ),
            ),
            (
                "personen",
                count(
                    PersonOrganisatieEenheid,
                    PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid_id,
                    placement_not_ended(),
                ),
            ),
        ]
    return queries


async def eenheid_references(
    session: AsyncSession, eenheid_id: UUID, *, structure: bool = False
) -> list[str]:
    """What refers to *eenheid_id*, as ``"<n> <label>"`` parts (empty: nothing).

    Without *structure*: what its members reach through it (resources in
    it, grants it holds, shares from or to it).  With *structure* also the
    eenheden below it and its placements: everything that deleting it would
    cascade away or leave without an eenheid (which makes it tenant-wide).
    """
    parts = []
    for label, stmt in _reference_queries(eenheid_id, structure=structure):
        n = await session.scalar(stmt)
        if n:
            parts.append(f"{n} {label}")
    return parts
