"""Initiatief-based access context for leads visibility filtering.

Determines which initiatieven a user can see based on:
- Direct membership (InitiatiefMember)
- Organisatie-eenheid membership (InitiatiefEenheid + PersonOrganisatieEenheid)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.initiatief import InitiatiefEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission

logger = logging.getLogger(__name__)


@dataclass
class InitiatiefContext:
    """Initiatief-based access context for the current user."""

    person_id: UUID | None = None
    visible_initiatief_ids: list[UUID] = field(default_factory=list)
    is_admin: bool = False
    is_authenticated: bool = False


async def build_initiatief_context(
    db: AsyncSession,
    person: Person,
) -> InitiatiefContext:
    """Build an InitiatiefContext for the given person.

    Queries direct membership and team-based membership to determine
    which initiatieven are visible.
    """
    if person.is_admin:
        return InitiatiefContext(
            person_id=person.id,
            is_admin=True,
            is_authenticated=True,
        )

    # Direct membership via resource_permission
    direct_stmt = select(ResourcePermission.resource_id).where(
        ResourcePermission.resource_type == "initiatief",
        ResourcePermission.person_id == person.id,
    )

    # Via organisatie-eenheid membership
    today = date.today()
    eenheid_stmt = (
        select(InitiatiefEenheid.initiatief_id)
        .join(
            PersonOrganisatieEenheid,
            PersonOrganisatieEenheid.organisatie_eenheid_id
            == InitiatiefEenheid.eenheid_id,
        )
        .where(
            PersonOrganisatieEenheid.person_id == person.id,
            PersonOrganisatieEenheid.start_datum <= today,
            or_(
                PersonOrganisatieEenheid.eind_datum.is_(None),
                PersonOrganisatieEenheid.eind_datum >= today,
            ),
        )
    )

    # Union of both
    combined = union(direct_stmt, eenheid_stmt)
    result = await db.execute(combined)
    visible_ids = list(result.scalars().all())

    return InitiatiefContext(
        person_id=person.id,
        visible_initiatief_ids=visible_ids,
        is_admin=False,
        is_authenticated=True,
    )


async def get_initiatief_context(
    request: Request,
    person: Person | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> InitiatiefContext:
    """FastAPI dependency that returns the InitiatiefContext for the current user.

    Results are cached on the request state to avoid re-computation when
    the dependency is used multiple times in a single request.
    """
    cached = getattr(request.state, "initiatief_context", None)
    if cached is not None:
        return cached

    if person is None:
        from bouwmeester.core.config import get_settings

        settings = get_settings()
        if not settings.OIDC_ISSUER:
            ctx = InitiatiefContext(is_admin=True, is_authenticated=True)
        else:
            ctx = InitiatiefContext(is_authenticated=False)
    else:
        ctx = await build_initiatief_context(db, person)

    request.state.initiatief_context = ctx
    return ctx


def apply_initiatief_filter(stmt, column, ctx: InitiatiefContext | None):
    """Apply initiatief-based visibility filter to a SQLAlchemy select statement.

    Args:
        stmt: SQLAlchemy select statement.
        column: The initiatief_id column to filter on.
        ctx: InitiatiefContext, or None (no filtering applied).

    Returns:
        The statement with an additional WHERE clause, or unmodified if
        no filtering is needed.
    """
    if ctx is None or ctx.is_admin:
        return stmt
    if not ctx.is_authenticated:
        # Unauthenticated: show nothing
        return stmt.where(column.is_(None))
    # Show leads from user's initiatieven + leads without initiatief
    # (so they can be assigned to an initiatief during migration)
    return stmt.where(
        or_(
            column.in_(ctx.visible_initiatief_ids),
            column.is_(None),
        )
    )
