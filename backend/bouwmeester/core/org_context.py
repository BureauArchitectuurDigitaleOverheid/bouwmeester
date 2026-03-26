"""Org-chart-based access context for visibility filtering.

Determines which organisatie-eenheden a user can see based on their
position in the org hierarchy: own memberships, parent chain, and
managed sub-trees.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

logger = logging.getLogger(__name__)


@dataclass
class OrgContext:
    """Org-chart-based access context for the current user."""

    person_id: UUID | None = None
    own_eenheid_ids: list[UUID] = field(default_factory=list)
    visible_eenheid_ids: list[UUID] = field(default_factory=list)
    is_admin: bool = False
    is_authenticated: bool = False


async def _get_own_eenheid_ids(
    db: AsyncSession,
    person_id: UUID,
) -> list[UUID]:
    """Return eenheid IDs where the person is currently an active member."""
    today = date.today()
    stmt = select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
        PersonOrganisatieEenheid.person_id == person_id,
        PersonOrganisatieEenheid.start_datum <= today,
        or_(
            PersonOrganisatieEenheid.eind_datum.is_(None),
            PersonOrganisatieEenheid.eind_datum >= today,
        ),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _walk_parents(
    db: AsyncSession,
    eenheid_ids: list[UUID],
) -> set[UUID]:
    """Walk up the parent chain for each eenheid and collect all parent IDs."""
    collected: set[UUID] = set()
    to_visit = set(eenheid_ids)

    while to_visit:
        stmt = select(OrganisatieEenheid.id, OrganisatieEenheid.parent_id).where(
            OrganisatieEenheid.id.in_(to_visit)
        )
        result = await db.execute(stmt)
        rows = result.all()

        next_visit: set[UUID] = set()
        for row in rows:
            if row.parent_id is not None and row.parent_id not in collected:
                collected.add(row.parent_id)
                next_visit.add(row.parent_id)

        to_visit = next_visit

    return collected


async def _get_managed_eenheid_ids(
    db: AsyncSession,
    person_id: UUID,
) -> list[UUID]:
    """Return eenheid IDs where the person is the (legacy) manager."""
    stmt = select(OrganisatieEenheid.id).where(
        OrganisatieEenheid.manager_id == person_id,
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _walk_children(
    db: AsyncSession,
    eenheid_ids: list[UUID],
) -> set[UUID]:
    """Recursively collect all descendant eenheid IDs."""
    collected: set[UUID] = set()
    to_visit = set(eenheid_ids)

    while to_visit:
        stmt = select(OrganisatieEenheid.id).where(
            OrganisatieEenheid.parent_id.in_(to_visit),
        )
        result = await db.execute(stmt)
        children = set(result.scalars().all())

        new_children = children - collected
        collected.update(new_children)
        to_visit = new_children

    return collected


async def build_org_context(
    db: AsyncSession,
    person: Person,
) -> OrgContext:
    """Build an OrgContext for the given person.

    Queries the org hierarchy to determine visibility:
    - Own memberships (active plaatsingen)
    - Parent chain (walking up from each own eenheid)
    - Managed sub-trees (walking down from eenheden where person is manager)
    """
    if person.is_admin:
        return OrgContext(
            person_id=person.id,
            is_admin=True,
            is_authenticated=True,
        )

    own_ids = await _get_own_eenheid_ids(db, person.id)
    parent_ids = await _walk_parents(db, own_ids)

    managed_ids = await _get_managed_eenheid_ids(db, person.id)
    managed_sub_ids = await _walk_children(db, managed_ids)

    all_visible = set(own_ids) | parent_ids | set(managed_ids) | managed_sub_ids

    return OrgContext(
        person_id=person.id,
        own_eenheid_ids=own_ids,
        visible_eenheid_ids=list(all_visible),
        is_admin=False,
        is_authenticated=True,
    )


async def get_org_context(
    request: Request,
    person: Person | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> OrgContext:
    """FastAPI dependency that returns the OrgContext for the current user.

    Results are cached on the request state to avoid re-computation when
    the dependency is used multiple times in a single request.
    """
    cached = getattr(request.state, "org_context", None)
    if cached is not None:
        return cached

    if person is None:
        ctx = OrgContext(is_authenticated=False)
    else:
        ctx = await build_org_context(db, person)

    request.state.org_context = ctx
    return ctx


def apply_org_filter(stmt, column, ctx: OrgContext | None):
    """Apply org-based visibility filter to a SQLAlchemy select statement.

    Args:
        stmt: SQLAlchemy select statement.
        column: The organisatie_eenheid_id column to filter on.
        ctx: OrgContext, or None (no filtering applied).

    Returns:
        The statement with an additional WHERE clause, or unmodified if
        no filtering is needed.
    """
    if ctx is None or ctx.is_admin:
        return stmt
    if not ctx.is_authenticated:
        return stmt.where(column.is_(None))
    return stmt.where(
        or_(
            column.is_(None),
            column.in_(ctx.visible_eenheid_ids),
        )
    )
