"""The single decision point: may this person do this action on this resource?

AuthZEN-shaped: a *subject* (``PermissionContext``), an *action* (a
permission string such as ``"node:update"``) and a *resource* (a type plus
an id, or a type plus the eenheid it will live in when it does not exist
yet).  Routes and chat tools ask here; they do not combine
``require_permission`` with ``check_org_scope`` themselves.

Public API (keep it this small)::

    await can(db, perm_ctx, "node:update", "corpus_node", node_id) -> bool
    await require(db, perm_ctx, "node:update", "corpus_node", node_id)  # 401/403/404
    Depends(requires("node:update", "corpus_node", path_param="id"))

Creating something: pass the eenheid it goes into (``eenheid_id=``), or ask
about its parent with the child's permission
(``require(db, ctx, "edge:create", "corpus_node", from_node_id)``): a
child permission on a parent is decided as write access on that parent.

Rule of the model: seeing never implies writing, and a permission only
counts where it holds.  ``core.org_context`` still decides visibility (read
up the line, shares); this module decides actions.  ``core.authority``
builds on it for decisions about grants.

Resolution order (first match wins; every step can only allow):

1. super_admin, or *permission* from a system-level role.
2. A resource role on the resource itself (``ResourcePermission``, direct or
   through an eenheid the person is placed in), mapped through
   ``RESOURCE_ROLE_PERMISSIONS``.
3. Parent delegation (``DELEGATIONS`` below): the resource's rights come
   from its parent.  The permission is translated to the parent's domain:
   ``read`` stays ``read``, ``create``/``update`` become ``update``,
   ``delete`` becomes the parent verb named in the table.
4. *permission* held on the resource's eenheid (or on one above it: a role
   applies to everything below it), see ``rights_on_eenheid``.  For
   ``corpus_node`` and ``task`` an active *edit* share of that eenheid (or
   node) to an eenheid you are placed in counts as well, with the rights you
   hold there.  Read shares only give visibility.
5. Tenant-wide fallback, only for the types in ``TENANT_WIDE_WHEN_UNSCOPED``
   and only when the resource has no eenheid and no parent: *permission*
   held through any role, anywhere.

Delegation table (child -> parent; any parent suffices):

====================== ===================================== ==============
child type             parent                                child delete
====================== ===================================== ==============
edge                   corpus_node (from-node or to-node)    node:delete
task                   corpus_node, only if the task has no  node:update
                       eenheid (a team task is its team's)
lead                   initiatief (if set)                   initiatief:delete
initiatief_update      initiatief                            initiatief:update
lead_column            initiatief                            initiatief:update
lead_update            lead                                  lead:update
lead_activity          lead                                  lead:update
lead_attachment        lead                                  lead:update
parlementair_abonnement  scope: initiatief or lead           <parent>:update
mattermost_channel_link  scope: initiatief or lead           <parent>:update
github_link            scope: initiatief or lead             <parent>:update
stakeholder_assessment scope: corpus_node or initiatief      <parent>:update
====================== ===================================== ==============

Edges: an edge is a relation of both nodes, so the editors of either end may
maintain it; the other end only has to exist (the corpus is readable
tenant-wide).  Sub-records without an RBAC permission of their own use
``"<type>:<verb>"`` (``"lead_column:update"``) and are decided entirely by
their parent.

Tenant-wide fallbacks (step 5):

=========== ==============================================================
corpus_node Product decision: the corpus is tenant-wide.  A node with an
            eenheid is written by rights on that eenheid; a node without
            one by anyone holding the permission through any role.
lead        A lead without initiatief and without eenheid (migration
            period, see ``leads._check_lead_access``).
tag         Tags are one shared vocabulary without an eenheid.
=========== ==============================================================
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    RESOURCE_ROLE_PERMISSIONS,
    PermissionContext,
    check_resource_permission,
    get_permission_context,
)
from bouwmeester.models.edge import Edge
from bouwmeester.models.github_link import GitHubLink
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.models.tag import Tag
from bouwmeester.models.task import Task
from bouwmeester.repositories.org_tree import (
    get_membership_ids,
    get_self_and_ancestor_ids,
)
from bouwmeester.repositories.resource_scope import get_authority_eenheid_ids

# ---------------------------------------------------------------------------
# Rights on an eenheid (step 4; also the base of core.authority)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EenheidRights:
    """Roles and permissions a person effectively holds on one eenheid."""

    roles: frozenset[str]
    permissions: frozenset[str]
    is_super_admin: bool

    def has(self, perm: str) -> bool:
        return self.is_super_admin or perm in self.permissions

    def has_role(self, *roles: str) -> bool:
        return self.is_super_admin or bool(self.roles & set(roles))


async def rights_on_eenheid(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid_id: UUID,
    *,
    include_system_roles: bool = True,
) -> EenheidRights:
    """Resolve what *perm_ctx* may do on *eenheid_id*, inheriting downward.

    ``include_system_roles=False`` leaves out system roles other than
    super_admin, for decisions that belong to the organisation rather than
    to platform operators (who manages whom).
    """
    if perm_ctx.is_super_admin:
        return EenheidRights(frozenset(), frozenset(), is_super_admin=True)

    roles: set[str] = set(perm_ctx.system_roles) if include_system_roles else set()
    permissions: set[str] = (
        set(perm_ctx.system_permissions) if include_system_roles else set()
    )
    for eid in await _chain(db, perm_ctx, eenheid_id):
        roles.update(perm_ctx.scoped_roles.get(eid, ()))
        permissions |= perm_ctx.scoped_permissions.get(eid, set())
    return EenheidRights(frozenset(roles), frozenset(permissions), False)


async def _chain(db: AsyncSession, perm_ctx: PermissionContext, eid: UUID) -> set[UUID]:
    key = ("chain", eid)
    if key not in perm_ctx.authz_cache:
        perm_ctx.authz_cache[key] = await get_self_and_ancestor_ids(db, eid)
    return perm_ctx.authz_cache[key]


# ---------------------------------------------------------------------------
# Where a resource lives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Location:
    eenheid_ids: tuple[UUID, ...] = ()
    parents: tuple[tuple[str, UUID], ...] = ()
    node_id: UUID | None = None  # the node itself, for node shares


Locator = Callable[[AsyncSession, UUID], Awaitable[_Location | None]]


@dataclass(frozen=True)
class Delegation:
    parent_types: tuple[str, ...]
    locate: Locator
    delete_verb: str = "update"


async def _row(db: AsyncSession, *columns: Any, where: Any) -> Any:
    return (await db.execute(select(*columns).where(where))).one_or_none()


def _parent_column(model: Any, parent_type: str, column: Any) -> Locator:
    async def locate(db: AsyncSession, rid: UUID) -> _Location | None:
        row = await _row(db, column, where=model.id == rid)
        if row is None:
            return None
        return _Location(parents=((parent_type, row[0]),) if row[0] else ())

    return locate


def _scope_columns(model: Any) -> Locator:
    async def locate(db: AsyncSession, rid: UUID) -> _Location | None:
        row = await _row(db, model.scope_type, model.scope_id, where=model.id == rid)
        if row is None:
            return None
        return _Location(parents=((str(row[0]), row[1]),))

    return locate


async def _locate_edge(db: AsyncSession, rid: UUID) -> _Location | None:
    row = await _row(db, Edge.from_node_id, Edge.to_node_id, where=Edge.id == rid)
    if row is None:
        return None
    return _Location(parents=(("corpus_node", row[0]), ("corpus_node", row[1])))


async def _locate_task(db: AsyncSession, rid: UUID) -> _Location | None:
    row = await _row(
        db, Task.node_id, Task.organisatie_eenheid_id, where=Task.id == rid
    )
    if row is None:
        return None
    node_id, eenheid_id = row
    if eenheid_id is not None:
        return _Location(eenheid_ids=(eenheid_id,))
    return _Location(parents=(("corpus_node", node_id),))


async def _locate_lead(db: AsyncSession, rid: UUID) -> _Location | None:
    found, eenheid_ids = await get_authority_eenheid_ids(db, "lead", rid)
    if not found:
        return None
    lead = await db.get(Lead, rid)  # already in the identity map
    parents = (("initiatief", lead.initiatief_id),) if lead.initiatief_id else ()
    return _Location(eenheid_ids=tuple(eenheid_ids), parents=parents)


# The delegation table; see the module docstring for the same in prose.
DELEGATIONS: dict[str, Delegation] = {
    "edge": Delegation(("corpus_node",), _locate_edge, delete_verb="delete"),
    "task": Delegation(("corpus_node",), _locate_task),
    "lead": Delegation(("initiatief",), _locate_lead, delete_verb="delete"),
    "initiatief_update": Delegation(
        ("initiatief",),
        _parent_column(
            InitiatiefUpdatePost, "initiatief", InitiatiefUpdatePost.initiatief_id
        ),
    ),
    "lead_column": Delegation(
        ("initiatief",),
        _parent_column(LeadColumn, "initiatief", LeadColumn.initiatief_id),
    ),
    "lead_update": Delegation(
        ("lead",), _parent_column(LeadUpdatePost, "lead", LeadUpdatePost.lead_id)
    ),
    "lead_activity": Delegation(
        ("lead",), _parent_column(LeadActivity, "lead", LeadActivity.lead_id)
    ),
    "lead_attachment": Delegation(
        ("lead",), _parent_column(LeadAttachment, "lead", LeadAttachment.lead_id)
    ),
    "parlementair_abonnement": Delegation(
        ("initiatief", "lead"), _scope_columns(ParlementairAbonnement)
    ),
    "mattermost_channel_link": Delegation(
        ("initiatief", "lead"), _scope_columns(MattermostChannelLink)
    ),
    "github_link": Delegation(("initiatief", "lead"), _scope_columns(GitHubLink)),
    "stakeholder_assessment": Delegation(
        ("corpus_node", "initiatief"), _scope_columns(StakeholderAssessment)
    ),
}

# Types that live in an eenheid (resolved by ``resource_scope``).
_EENHEID_TYPES = frozenset(
    {"corpus_node", "initiatief", "opdracht", "organisatie_eenheid"}
)

# Types that live nowhere in particular: only their existence is looked up.
_PLAIN_TYPES: dict[str, Any] = {"tag": Tag}

TENANT_WIDE_WHEN_UNSCOPED = frozenset({"corpus_node", "lead", "tag"})

# Types whose eenheid can be shared for editing (``SharedAccess``).
_SHAREABLE_TYPES = frozenset({"corpus_node", "task"})

# Permission prefix per resource type where they differ.
_PERM_DOMAIN = {"corpus_node": "node", "organisatie_eenheid": "org"}
_DOMAIN_TYPE = {v: k for k, v in _PERM_DOMAIN.items()}


async def _locate(
    db: AsyncSession, perm_ctx: PermissionContext, resource_type: str, rid: UUID
) -> _Location | None:
    key = ("loc", resource_type, rid)
    if key in perm_ctx.authz_cache:
        return perm_ctx.authz_cache[key]
    if resource_type in DELEGATIONS:
        loc = await DELEGATIONS[resource_type].locate(db, rid)
    elif resource_type in _EENHEID_TYPES:
        found, eenheid_ids = await get_authority_eenheid_ids(db, resource_type, rid)
        loc = (
            _Location(
                eenheid_ids=tuple(eenheid_ids),
                node_id=rid if resource_type == "corpus_node" else None,
            )
            if found
            else None
        )
    elif resource_type in _PLAIN_TYPES:
        model = _PLAIN_TYPES[resource_type]
        found = await _row(db, model.id, where=model.id == rid)
        loc = _Location() if found is not None else None
    else:
        raise ValueError(f"authz: unknown resource type {resource_type!r}")
    perm_ctx.authz_cache[key] = loc
    return loc


def _parent_permission(
    permission: str, child_type: str, parent_type: str
) -> str | None:
    """Translate a child's permission to the one needed on its parent."""
    verb = permission.partition(":")[2]
    if verb == "read":
        parent_verb = "read"
    elif verb in ("create", "update"):
        parent_verb = "update"
    elif verb == "delete":
        parent_verb = DELEGATIONS[child_type].delete_verb
    else:
        return None
    return f"{_PERM_DOMAIN.get(parent_type, parent_type)}:{parent_verb}"


def _child_type_of(permission: str, resource_type: str) -> str | None:
    """The child type when *permission* is about a child of *resource_type*."""
    domain = permission.partition(":")[0]
    child = _DOMAIN_TYPE.get(domain, domain)
    if child == resource_type or child not in DELEGATIONS:
        return None
    return child if resource_type in DELEGATIONS[child].parent_types else None


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


async def _holds_on_eenheden(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    eenheid_ids: tuple[UUID, ...],
) -> bool:
    for eid in eenheid_ids:
        if (await rights_on_eenheid(db, perm_ctx, eid)).has(permission):
            return True
    return False


async def _holds_via_edit_share(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    loc: _Location,
) -> bool:
    """Step 4b: an edit share lets a target eenheid work with its own rights."""
    if perm_ctx.person_id is None:
        return False
    sources = [SharedAccess.source_eenheid_id.in_(loc.eenheid_ids)]
    if loc.node_id is not None:
        sources.append(SharedAccess.source_node_id == loc.node_id)
    own = await get_membership_ids(db, perm_ctx.person_id)
    if not own:
        return False
    today = date.today()
    targets = (
        await db.scalars(
            select(SharedAccess.target_eenheid_id).where(
                or_(*sources),
                SharedAccess.target_eenheid_id.in_(own),
                SharedAccess.access_level == "edit",
                SharedAccess.geldig_van <= today,
                or_(
                    SharedAccess.geldig_tot.is_(None), SharedAccess.geldig_tot >= today
                ),
            )
        )
    ).all()
    return await _holds_on_eenheden(db, perm_ctx, permission, tuple(set(targets)))


async def _decide(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None,
    eenheid_id: UUID | None,
) -> bool | None:
    """True/False, or None when the resource does not exist."""
    key = ("decision", permission, resource_type, resource_id, eenheid_id)
    if key in perm_ctx.authz_cache:
        return perm_ctx.authz_cache[key]
    result = await _resolve(
        db, perm_ctx, permission, resource_type, resource_id, eenheid_id
    )
    perm_ctx.authz_cache[key] = result
    return result


async def _resolve(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None,
    eenheid_id: UUID | None,
) -> bool | None:
    if resource_id is None:
        loc = _Location(eenheid_ids=(eenheid_id,) if eenheid_id else ())
    else:
        loc = await _locate(db, perm_ctx, resource_type, resource_id)
        if loc is None:
            return None

    # 1. System level.
    if perm_ctx.has_system_permission(permission):
        return True

    # A child's permission asked on its parent ("edge:create" on a node) is
    # write access on that parent.
    child = _child_type_of(permission, resource_type)
    if child is not None:
        parent_perm = _parent_permission(permission, child, resource_type)
        if parent_perm is None:
            return False
        return bool(
            await _decide(
                db, perm_ctx, parent_perm, resource_type, resource_id, eenheid_id
            )
        )

    # 2. A resource role on the resource itself.
    role_perms = RESOURCE_ROLE_PERMISSIONS.get(resource_type, {})
    if (
        resource_id is not None
        and perm_ctx.person_id is not None
        and any(permission in granted for granted in role_perms.values())
        and await check_resource_permission(
            db, perm_ctx.person_id, resource_type, resource_id, permission
        )
    ):
        return True

    # 3. Parent delegation.
    for parent_type, parent_id in loc.parents:
        parent_perm = _parent_permission(permission, resource_type, parent_type)
        if parent_perm is not None and await _decide(
            db, perm_ctx, parent_perm, parent_type, parent_id, None
        ):
            return True

    # 4. Rights on the resource's eenheid, inherited downward; edit shares.
    if await _holds_on_eenheden(db, perm_ctx, permission, loc.eenheid_ids):
        return True
    if (
        resource_type in _SHAREABLE_TYPES
        and (loc.eenheid_ids or loc.node_id)
        and await _holds_via_edit_share(db, perm_ctx, permission, loc)
    ):
        return True

    # 5. Tenant-wide fallback for resources that live nowhere in particular.
    return (
        resource_type in TENANT_WIDE_WHEN_UNSCOPED
        and not loc.eenheid_ids
        and not loc.parents
        and perm_ctx.has_permission(permission)
    )


async def can(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None = None,
    *,
    eenheid_id: UUID | None = None,
) -> bool:
    """May *perm_ctx* do *permission* on this resource?

    Pass ``resource_id`` for an existing resource, or ``eenheid_id`` (or
    nothing) for one about to be created.  A missing resource is ``False``.
    """
    if not perm_ctx.is_authenticated:
        return False
    return bool(
        await _decide(db, perm_ctx, permission, resource_type, resource_id, eenheid_id)
    )


async def require(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None = None,
    *,
    eenheid_id: UUID | None = None,
) -> None:
    """Like :func:`can`, but raises 401, 404 (resource missing) or 403."""
    if not perm_ctx.is_authenticated:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Niet ingelogd")
    decision = await _decide(
        db, perm_ctx, permission, resource_type, resource_id, eenheid_id
    )
    if decision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item niet gevonden")
    if not decision:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Je hebt hier geen rechten voor: je rechten gelden alleen binnen je "
            "eigen organisatie-eenheden en de items waar je een rol op hebt",
        )


def requires(permission: str, resource_type: str, *, path_param: str = "id"):
    """Dependency factory: ``require`` with the resource id from the path.

    Usage::

        @router.put("/{id}")
        async def update(
            id: UUID,
            perm_ctx: PermissionContext = Depends(
                requires("node:update", "corpus_node")
            ),
        ): ...
    """

    async def _authz_requires(
        request: Request,
        db: AsyncSession = Depends(get_db),
        perm_ctx: PermissionContext = Depends(get_permission_context),
    ) -> PermissionContext:
        try:
            resource_id = UUID(str(request.path_params[path_param]))
        except (KeyError, ValueError):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Ongeldige {path_param}"
            )
        await require(db, perm_ctx, permission, resource_type, resource_id)
        return perm_ctx

    return _authz_requires
