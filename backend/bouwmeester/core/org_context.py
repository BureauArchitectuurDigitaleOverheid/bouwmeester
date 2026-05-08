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

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole

logger = logging.getLogger(__name__)


@dataclass
class OrgContext:
    """Org-chart-based access context for the current user."""

    person_id: UUID | None = None
    own_eenheid_ids: list[UUID] = field(default_factory=list)
    managed_eenheid_ids: list[UUID] = field(default_factory=list)
    visible_eenheid_ids: list[UUID] = field(default_factory=list)
    shared_eenheid_ids: list[UUID] = field(default_factory=list)
    shared_node_ids: list[UUID] = field(default_factory=list)
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
    """Return eenheid IDs where the person manages the sub-tree.

    Includes both unit_manager and ministry_admin roles, since both
    grant visibility over the eenheid and its descendants.
    """
    today = date.today()
    stmt = select(PersonRole.organisatie_eenheid_id).where(
        PersonRole.person_id == person_id,
        PersonRole.role_id.in_(["unit_manager", "ministry_admin"]),
        PersonRole.organisatie_eenheid_id.isnot(None),
        PersonRole.start_datum <= today,
        or_(
            PersonRole.eind_datum.is_(None),
            PersonRole.eind_datum >= today,
        ),
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
    *,
    perm_ctx=None,
) -> OrgContext:
    """Build an OrgContext for the given person.

    Queries the org hierarchy to determine visibility:
    - Own memberships (active plaatsingen)
    - Parent chain (walking up from each own eenheid)
    - Managed sub-trees (walking down from eenheden where person is manager)

    Pass an existing *perm_ctx* (a ``PermissionContext``) to avoid a
    redundant ``build_permission_context`` call when the caller already
    has one.
    """
    from bouwmeester.core.permissions import build_permission_context

    if perm_ctx is None:
        perm_ctx = await build_permission_context(db, person)
    if perm_ctx.is_super_admin:
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

    # Query shared access grants targeting the user's eenheden
    from bouwmeester.repositories.shared_access import SharedAccessRepository

    sa_repo = SharedAccessRepository(db)
    shared_eenheid_ids = await sa_repo.get_shared_eenheid_ids(own_ids)
    shared_node_ids = await sa_repo.get_shared_node_ids(own_ids)

    return OrgContext(
        person_id=person.id,
        own_eenheid_ids=own_ids,
        managed_eenheid_ids=managed_ids,
        visible_eenheid_ids=list(all_visible),
        shared_eenheid_ids=shared_eenheid_ids,
        shared_node_ids=shared_node_ids,
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
        # In dev mode (no OIDC), treat as admin so all data is visible
        from bouwmeester.core.config import get_settings

        settings = get_settings()
        if not settings.OIDC_ISSUER:
            ctx = OrgContext(is_admin=True, is_authenticated=True)
        else:
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
    all_visible = list(set(ctx.visible_eenheid_ids) | set(ctx.shared_eenheid_ids))
    return stmt.where(
        or_(
            column.is_(None),
            column.in_(all_visible),
        )
    )


def org_filter_sql_clause(column: str, ctx: OrgContext | None) -> str:
    """Return a raw SQL AND clause for org-based visibility filtering.

    Raw SQL variant of :func:`apply_org_filter` for use in queries that
    cannot be expressed with the SQLAlchemy ORM (e.g. UNION ALL across
    heterogeneous tables).

    Args:
        column: SQL column name (e.g. ``"organisatie_eenheid_id"``).
        ctx: OrgContext, or None (no filtering applied).

    Returns:
        An ``" AND ..."`` SQL fragment, or ``""`` when no filtering is needed.
    """
    if ctx is None or ctx.is_admin:
        return ""
    if not ctx.is_authenticated:
        return f" AND {column} IS NULL"
    all_visible = list(set(ctx.visible_eenheid_ids) | set(ctx.shared_eenheid_ids))
    if not all_visible:
        return f" AND {column} IS NULL"
    return f" AND ({column} IS NULL OR {column} = ANY(:visible_eenheid_ids))"


# ---------------------------------------------------------------------------
# Write-side scope enforcement
# ---------------------------------------------------------------------------


def check_org_scope(
    eenheid_id: UUID | None,
    org_ctx: OrgContext,
    *,
    allow_none: bool = True,
) -> None:
    """Raise 403 if *eenheid_id* is outside the user's visible org scope.

    Call this in write endpoints before creating or mutating a resource
    that belongs to an organisatie-eenheid.

    Args:
        eenheid_id: The organisatie-eenheid to check (``None`` = no scope).
        org_ctx: The org context for the current user.
        allow_none: If ``True`` (default), ``None`` eenheid_id is always
            allowed.  Set to ``False`` to require an eenheid.
    """
    if eenheid_id is None:
        if allow_none:
            return
        raise HTTPException(status_code=403, detail="Organisatie-eenheid is verplicht")
    if org_ctx.is_admin:
        return
    all_visible = set(org_ctx.visible_eenheid_ids) | set(org_ctx.shared_eenheid_ids)
    if eenheid_id not in all_visible:
        raise HTTPException(
            status_code=403,
            detail="Geen toegang tot deze organisatie-eenheid",
        )


async def check_resource_org_scope(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
    org_ctx: OrgContext,
) -> None:
    """Resolve the org unit for a resource and check org scope in one step.

    Raises 404 if the resource does not exist, 403 if the resource's
    eenheid is outside the caller's visible scope.
    """
    found, eenheid_id = await resolve_resource_eenheid_id(
        db, resource_type, resource_id
    )
    if not found:
        raise HTTPException(status_code=404, detail=f"{resource_type} not found")
    check_org_scope(eenheid_id, org_ctx)


async def resolve_resource_eenheid_id(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
) -> tuple[bool, UUID | None]:
    """Resolve the organisatie_eenheid_id for a polymorphic resource.

    Returns ``(found, eenheid_id)`` — *found* is ``False`` when the
    resource does not exist (distinguishing from a resource that exists
    but has no eenheid assigned).
    """
    if resource_type == "corpus_node":
        from bouwmeester.models.corpus_node import CorpusNode

        stmt = select(CorpusNode.organisatie_eenheid_id).where(
            CorpusNode.id == resource_id
        )
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "organisatie_eenheid":
        from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

        stmt = select(OrganisatieEenheid.id).where(OrganisatieEenheid.id == resource_id)
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "opdracht":
        from bouwmeester.models.opdracht import Opdracht

        stmt = select(Opdracht.opdrachtgever_id).where(Opdracht.id == resource_id)
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "task":
        from bouwmeester.models.task import Task

        stmt = select(Task.organisatie_eenheid_id).where(Task.id == resource_id)
        result = await db.execute(stmt)
        row = result.one_or_none()
        return (True, row[0]) if row is not None else (False, None)

    if resource_type == "initiatief":
        from bouwmeester.models.resource_permission import ResourcePermission

        stmt = select(ResourcePermission.organisatie_eenheid_id).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id == resource_id,
            ResourcePermission.organisatie_eenheid_id.isnot(None),
        )
        result = await db.execute(stmt)
        first = result.scalars().first()
        return (True, first)

    if resource_type == "lead":
        from bouwmeester.models.lead import Lead
        from bouwmeester.models.resource_permission import ResourcePermission

        stmt = (
            select(ResourcePermission.organisatie_eenheid_id)
            .join(Lead, Lead.initiatief_id == ResourcePermission.resource_id)
            .where(
                Lead.id == resource_id,
                ResourcePermission.resource_type == "initiatief",
                ResourcePermission.organisatie_eenheid_id.isnot(None),
            )
        )
        result = await db.execute(stmt)
        first = result.scalars().first()
        return (True, first)

    return (False, None)
