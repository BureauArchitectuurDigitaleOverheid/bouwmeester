"""Who sees which eenheden, nodes, tasks and opdrachten (``core.authz`` step 0).

Each rule has a SQL form for lists (``apply_*_filter``) and a row form for
details (``sees_*``), side by side, so a list and a detail cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bouwmeester.core.authz import write_eenheid_ids
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.person import Person
from bouwmeester.repositories.org_tree import get_internal_ids, get_subtree_ids


@dataclass
class OrgContext:
    """Org-chart-based access context for the current user."""

    person_id: UUID | None = None
    own_eenheid_ids: list[UUID] = field(default_factory=list)
    managed_eenheid_ids: list[UUID] = field(default_factory=list)
    # The managed eenheden plus everything below them.
    visible_eenheid_ids: list[UUID] = field(default_factory=list)
    shared_eenheid_ids: list[UUID] = field(default_factory=list)
    shared_node_ids: list[UUID] = field(default_factory=list)
    # Resources the caller holds a resource role on that lets them read.
    role_node_ids: list[UUID] = field(default_factory=list)
    role_opdracht_ids: list[UUID] = field(default_factory=list)
    # The switchable modules (``core.authz._MODULE_GATED``) readable somewhere.
    readable_modules: frozenset[str] = frozenset()
    is_admin: bool = False
    is_authenticated: bool = False


async def build_org_context(
    db: AsyncSession,
    person: Person | None,
    *,
    perm_ctx: PermissionContext | None = None,
) -> OrgContext:
    """Build an OrgContext for the given person (pass *perm_ctx* if known).

    Visible: own memberships, the line above own internal eenheden, the
    subtrees where a scoped role writes, and shares to own eenheden.
    """
    from bouwmeester.core.authority import managed_eenheid_ids
    from bouwmeester.core.authz import (
        memberships,
        readable_modules,
        role_read_ids,
        self_and_ancestor_ids,
    )
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

    # Only the organisation reads up its line.
    own_ids = list(await memberships(db, perm_ctx))
    parent_ids = await self_and_ancestor_ids(
        db, perm_ctx, await get_internal_ids(db, own_ids)
    )
    managed_ids = managed_eenheid_ids(perm_ctx)
    # What you can write you see; this covers a manager's subtree too.
    writable_subtree = await get_subtree_ids(db, write_eenheid_ids(perm_ctx))

    all_visible = set(own_ids) | parent_ids | writable_subtree

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
        role_node_ids=await role_read_ids(db, perm_ctx, "corpus_node"),
        role_opdracht_ids=await role_read_ids(db, perm_ctx, "opdracht"),
        readable_modules=readable_modules(perm_ctx),
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
    """Restrict *stmt* to the rows the caller sees, by their eenheid *column*.

    A column of a corpus node or task (or an alias) applies that type's
    full rule (:func:`apply_node_filter`, :func:`apply_task_filter`).
    """
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.task import Task

    parent = getattr(column, "parent", None)  # the mapper or alias, if ORM
    model = getattr(parent, "class_", None)
    if model is CorpusNode:
        return apply_node_filter(stmt, ctx, parent.entity)
    if model is Task:
        return apply_task_filter(stmt, ctx, parent.entity)
    if ctx is None or ctx.is_admin:
        return stmt
    return stmt.where(org_eenheid_clause(column, ctx))


def _visible_ids(ctx: OrgContext) -> list[UUID]:
    return list(set(ctx.visible_eenheid_ids) | set(ctx.shared_eenheid_ids))


def org_eenheid_clause(column, ctx: OrgContext):
    """SQL for :func:`sees_eenheid` (no eenheid, or a visible one)."""
    visible = _visible_ids(ctx) if ctx.is_authenticated else []
    return or_(column.is_(None), column.in_(visible))


def _node_clause(node, ctx: OrgContext):
    """SQL for :func:`sees_node` on the entity *node* (``CorpusNode`` or an alias)."""
    if not ctx.is_authenticated:
        return node.organisatie_eenheid_id.is_(None)
    return or_(
        org_eenheid_clause(node.organisatie_eenheid_id, ctx),
        node.id.in_(set(ctx.role_node_ids) | set(ctx.shared_node_ids)),
    )


def apply_node_filter(stmt, ctx: OrgContext | None, node=None):
    """Restrict a select over corpus nodes to the visible ones (:func:`sees_node`)."""
    from bouwmeester.models.corpus_node import CorpusNode

    if ctx is None or ctx.is_admin:
        return stmt
    return stmt.where(_node_clause(node if node is not None else CorpusNode, ctx))


def apply_task_filter(stmt, ctx: OrgContext | None, task=None):
    """Restrict a select over tasks to the visible ones (:func:`sees_task`)."""
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.task import Task

    if ctx is None or ctx.is_admin:
        return stmt
    task = task if task is not None else Task
    if "task" not in ctx.readable_modules:
        if ctx.person_id is None:
            return stmt.where(false())
        return stmt.where(task.assignee_id == ctx.person_id)
    node = aliased(CorpusNode)
    node_visible = (
        select(node.id).where(node.id == task.node_id, _node_clause(node, ctx)).exists()
    )
    visible = _visible_ids(ctx)
    clauses = [
        task.organisatie_eenheid_id.in_(visible),
        and_(task.organisatie_eenheid_id.is_(None), node_visible),
    ]
    if ctx.person_id is not None:
        clauses.append(task.assignee_id == ctx.person_id)
    return stmt.where(or_(*clauses))


def apply_opdracht_filter(stmt, ctx: OrgContext | None):
    """Restrict a select over opdrachten to the visible ones (:func:`sees_opdracht`)."""
    from bouwmeester.models.opdracht import Opdracht

    if ctx is None or ctx.is_admin:
        return stmt
    if "opdracht" not in ctx.readable_modules:
        # Module off: only what a resource role on the opdracht itself gives.
        return stmt.where(Opdracht.id.in_(ctx.role_opdracht_ids))
    visible = _visible_ids(ctx)
    return stmt.where(
        or_(
            and_(
                Opdracht.opdrachtgever_id.is_(None),
                Opdracht.opdrachtnemer_eenheid_id.is_(None),
            ),
            Opdracht.opdrachtgever_id.in_(visible),
            Opdracht.opdrachtnemer_eenheid_id.in_(visible),
            Opdracht.id.in_(ctx.role_opdracht_ids),
        )
    )


def sees_eenheid(org_ctx: OrgContext, eenheid_id: UUID | None) -> bool:
    """Whether something in *eenheid_id* (or in none) is visible: one row of
    ``apply_org_filter``.
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


def sees_node(
    org_ctx: OrgContext, node_id: UUID | None, eenheid_id: UUID | None
) -> bool:
    """Whether a corpus node is visible: :func:`apply_node_filter` for one row."""
    if sees_eenheid(org_ctx, eenheid_id):
        return True
    return node_id is not None and (
        node_id in org_ctx.role_node_ids or node_id in org_ctx.shared_node_ids
    )


def sees_task(
    org_ctx: OrgContext, eenheid_id: UUID | None, assignee_id: UUID | None
) -> bool | None:
    """Whether a task is visible, or None when its node decides (no eenheid).

    :func:`apply_task_filter` for one row; the module gate is ``core.authz``'s.
    """
    if org_ctx.is_admin:
        return True
    if assignee_id is not None and assignee_id == org_ctx.person_id:
        return True
    if eenheid_id is None:
        return None
    return org_ctx.is_authenticated and sees_eenheid(org_ctx, eenheid_id)


def sees_opdracht(
    org_ctx: OrgContext, opdracht_id: UUID | None, eenheid_ids: tuple[UUID, ...]
) -> bool:
    """Whether an opdracht is visible: :func:`apply_opdracht_filter` for one row."""
    if org_ctx.is_admin:
        return True
    if not org_ctx.is_authenticated:
        return False
    if not eenheid_ids or any(sees_eenheid(org_ctx, e) for e in eenheid_ids):
        return True
    return opdracht_id is not None and opdracht_id in org_ctx.role_opdracht_ids
