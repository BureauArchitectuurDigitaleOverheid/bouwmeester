"""Org-chart-based access context for visibility filtering.

Determines which organisatie-eenheden a user can see based on their
position in the org hierarchy: own memberships, parent chain, and
managed sub-trees.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.person import Person
from bouwmeester.repositories.org_tree import get_ancestor_ids, get_membership_ids
from bouwmeester.repositories.resource_scope import resolve_resource_eenheid_id

logger = logging.getLogger(__name__)


@dataclass
class OrgContext:
    """Org-chart-based access context for the current user."""

    person_id: UUID | None = None
    own_eenheid_ids: list[UUID] = field(default_factory=list)
    managed_eenheid_ids: list[UUID] = field(default_factory=list)
    # The managed eenheden plus everything below them.
    managed_subtree_ids: list[UUID] = field(default_factory=list)
    visible_eenheid_ids: list[UUID] = field(default_factory=list)
    shared_eenheid_ids: list[UUID] = field(default_factory=list)
    shared_node_ids: list[UUID] = field(default_factory=list)
    is_admin: bool = False
    is_authenticated: bool = False


async def build_org_context(
    db: AsyncSession,
    person: Person | None,
    *,
    perm_ctx: PermissionContext | None = None,
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
    from bouwmeester.core.authority import managed_eenheid_ids, managed_subtree_ids
    from bouwmeester.core.permissions import (
        anonymous_permission_context,
        build_permission_context,
    )

    if person is None:
        # Dev mode sees everything; otherwise an anonymous request sees nothing.
        anon = perm_ctx or anonymous_permission_context()
        return OrgContext(
            is_admin=anon.is_super_admin, is_authenticated=anon.is_authenticated
        )
    if perm_ctx is None:
        perm_ctx = await build_permission_context(db, person)
    if perm_ctx.is_super_admin:
        return OrgContext(
            person_id=person.id,
            is_admin=True,
            is_authenticated=True,
        )

    own_ids = await get_membership_ids(db, person.id)
    parent_ids = await get_ancestor_ids(db, own_ids)
    managed_ids = managed_eenheid_ids(perm_ctx)
    managed_subtree = await managed_subtree_ids(db, perm_ctx) or set()

    all_visible = set(own_ids) | parent_ids | managed_subtree

    # Query shared access grants targeting the user's eenheden
    from bouwmeester.repositories.shared_access import SharedAccessRepository

    sa_repo = SharedAccessRepository(db)
    shared_eenheid_ids = await sa_repo.get_shared_eenheid_ids(own_ids)
    shared_node_ids = await sa_repo.get_shared_node_ids(own_ids)

    return OrgContext(
        person_id=person.id,
        own_eenheid_ids=own_ids,
        managed_eenheid_ids=managed_ids,
        managed_subtree_ids=list(managed_subtree),
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
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> OrgContext:
    """FastAPI dependency that returns the OrgContext for the current user.

    Results are cached on the request state to avoid re-computation when
    the dependency is used multiple times in a single request.
    """
    cached = getattr(request.state, "org_context", None)
    if cached is not None:
        return cached

    ctx = await build_org_context(db, person, perm_ctx=perm_ctx)

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
