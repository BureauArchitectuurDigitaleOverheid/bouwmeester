"""Initiatief-based access context for leads visibility filtering.

Determines which initiatieven a user can see based on:
- Direct membership (resource_permission with person_id set)
- Organisatie-eenheid membership (resource_permission with eenheid_id set
  + PersonOrganisatieEenheid)
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
from bouwmeester.core.permissions import PermissionContext, get_permission_context
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
    person: Person | None,
    *,
    perm_ctx: PermissionContext | None = None,
) -> InitiatiefContext:
    """Build an InitiatiefContext for the given person.

    Pass an existing *perm_ctx* to avoid building it a second time.
    """
    from bouwmeester.core.permissions import (
        anonymous_permission_context,
        build_permission_context,
    )

    if person is None:
        # Dev mode sees everything; otherwise an anonymous request sees nothing.
        anon = perm_ctx or anonymous_permission_context()
        return InitiatiefContext(
            is_admin=anon.is_super_admin, is_authenticated=anon.is_authenticated
        )
    if perm_ctx is None:
        perm_ctx = await build_permission_context(db, person)
    if perm_ctx.is_super_admin:
        return InitiatiefContext(
            person_id=person.id,
            is_admin=True,
            is_authenticated=True,
        )

    # Direct person-scoped membership
    direct_stmt = select(ResourcePermission.resource_id.label("initiatief_id")).where(
        ResourcePermission.resource_type == "initiatief",
        ResourcePermission.person_id == person.id,
    )

    # Via eenheid-scoped resource_permission + PersonOrganisatieEenheid
    today = date.today()
    eenheid_stmt = (
        select(ResourcePermission.resource_id.label("initiatief_id"))
        .join(
            PersonOrganisatieEenheid,
            PersonOrganisatieEenheid.organisatie_eenheid_id
            == ResourcePermission.organisatie_eenheid_id,
        )
        .where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.organisatie_eenheid_id.isnot(None),
            PersonOrganisatieEenheid.person_id == person.id,
            PersonOrganisatieEenheid.start_datum <= today,
            or_(
                PersonOrganisatieEenheid.eind_datum.is_(None),
                PersonOrganisatieEenheid.eind_datum >= today,
            ),
        )
    )

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
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefContext:
    """FastAPI dependency that returns the InitiatiefContext."""
    cached = getattr(request.state, "initiatief_context", None)
    if cached is not None:
        return cached

    ctx = await build_initiatief_context(db, person, perm_ctx=perm_ctx)

    request.state.initiatief_context = ctx
    return ctx


def apply_initiatief_filter(stmt, column, ctx: InitiatiefContext | None):
    """Apply initiatief-based visibility filter to a SQLAlchemy statement."""
    if ctx is None or ctx.is_admin:
        return stmt
    if not ctx.is_authenticated:
        return stmt.where(column.is_(None))
    return stmt.where(
        or_(
            column.in_(ctx.visible_initiatief_ids),
            column.is_(None),
        )
    )
