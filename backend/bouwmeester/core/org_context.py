"""Org-chart-based access context for visibility filtering.

Determines which organisatie-eenheden a user can see based on their
position in the org hierarchy: own memberships, parent chain, and
managed sub-trees.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import write_eenheid_ids
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.person import Person
from bouwmeester.repositories.org_tree import (
    get_ancestor_ids,
    get_membership_ids,
    get_subtree_ids,
)

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
    - Writable sub-trees (walking down from eenheden where a scoped role
      grants a write permission, see ``core.authz.write_eenheid_ids``)

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
    # Rights inherit downward (core.authz), so what you can write you see.
    # Managers write in what they manage, so this covers managed_subtree.
    writable_subtree = await get_subtree_ids(db, write_eenheid_ids(perm_ctx))

    all_visible = set(own_ids) | parent_ids | writable_subtree

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
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> OrgContext:
    """FastAPI dependency: the caller's OrgContext (``core.authz`` builds it once)."""
    from bouwmeester.core.authz import org_visibility

    return await org_visibility(db, perm_ctx)


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
    all_visible = _visible_ids(ctx)
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
    all_visible = _visible_ids(ctx)
    if not all_visible:
        return f" AND {column} IS NULL"
    return f" AND ({column} IS NULL OR {column} = ANY(:visible_eenheid_ids))"


def org_filter_sql_params(ctx: OrgContext | None) -> dict:
    """The bind parameters :func:`org_filter_sql_clause` refers to.

    Exactly the parameters the clause uses, so a caller whose only visible
    eenheden come from shares still binds ``visible_eenheid_ids``.
    """
    if ctx is None or ctx.is_admin or not ctx.is_authenticated:
        return {}
    all_visible = _visible_ids(ctx)
    if not all_visible:
        return {}
    return {"visible_eenheid_ids": [str(eid) for eid in all_visible]}


def _visible_ids(ctx: OrgContext) -> list[UUID]:
    return list(set(ctx.visible_eenheid_ids) | set(ctx.shared_eenheid_ids))


def apply_task_filter(stmt, ctx: OrgContext | None):
    """Restrict a select over ``Task`` to the visible tasks.

    A task with an eenheid is visible with that eenheid; a task without one
    is read through its node (``core.authz``), so the node must be visible.
    """
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.task import Task

    if ctx is None or ctx.is_admin:
        return stmt
    visible = _visible_ids(ctx) if ctx.is_authenticated else []
    node_visible = (
        select(CorpusNode.id)
        .where(
            CorpusNode.id == Task.node_id,
            or_(
                CorpusNode.organisatie_eenheid_id.is_(None),
                CorpusNode.organisatie_eenheid_id.in_(visible),
            ),
        )
        .exists()
    )
    return stmt.where(
        or_(
            Task.organisatie_eenheid_id.in_(visible),
            and_(Task.organisatie_eenheid_id.is_(None), node_visible),
        )
    )


def apply_opdracht_filter(stmt, ctx: OrgContext | None):
    """Restrict a select over ``Opdracht`` to the visible opdrachten.

    An opdracht is visible when its opdrachtgever or its opdrachtnemer-
    eenheid is visible, or when it has neither (``core.authz``).
    """
    from bouwmeester.models.opdracht import Opdracht

    if ctx is None or ctx.is_admin:
        return stmt
    visible = _visible_ids(ctx) if ctx.is_authenticated else []
    return stmt.where(
        or_(
            and_(
                Opdracht.opdrachtgever_id.is_(None),
                Opdracht.opdrachtnemer_eenheid_id.is_(None),
            ),
            Opdracht.opdrachtgever_id.in_(visible),
            Opdracht.opdrachtnemer_eenheid_id.in_(visible),
        )
    )


def sees_eenheid(org_ctx: OrgContext, eenheid_id: UUID | None) -> bool:
    """Whether something in *eenheid_id* is visible: ``apply_org_filter`` for one row.

    Something without an eenheid is visible to every authenticated user.
    """
    if org_ctx.is_admin:
        return True
    if not org_ctx.is_authenticated:
        return eenheid_id is None
    return (
        eenheid_id is None
        or eenheid_id in org_ctx.visible_eenheid_ids
        or eenheid_id in org_ctx.shared_eenheid_ids
    )


async def check_resource_org_scope(
    db: AsyncSession,
    resource_type: str,
    resource_id: UUID,
    org_ctx: OrgContext,
) -> None:
    """Deprecated: ask ``core.authz.require(..., "<type>:read", ...)`` instead.

    Kept only for callers outside the routes that still hold an OrgContext
    and no PermissionContext.  404 if the resource does not exist or none
    of its eenheden is visible.
    """
    from bouwmeester.core.authz import get_eenheid_ids

    found, eenheid_ids = await get_eenheid_ids(db, resource_type, resource_id)
    if not found or not (
        not eenheid_ids or any(sees_eenheid(org_ctx, e) for e in eenheid_ids)
    ):
        raise HTTPException(status_code=404, detail="Niet gevonden")
