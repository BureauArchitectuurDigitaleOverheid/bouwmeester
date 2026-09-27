"""The single decision point: may this person do this action on this resource?

AuthZEN-shaped: a *subject* (``PermissionContext``), an *action* (a
permission string such as ``"node:update"``) and a *resource* (a type plus
an id, or a type plus the place it will live in when it does not exist
yet).  Routes and chat tools ask here; they do not combine
``require_permission`` with visibility checks themselves.

Public API (keep it this small)::

    await can(db, perm_ctx, "node:update", "corpus_node", node_id) -> bool
    await require(db, perm_ctx, "node:update", "corpus_node", node_id)
    Depends(requires("node:update", "corpus_node", path_param="id"))
    await can_anywhere(db, perm_ctx, "task:create", "task") -> bool
    await require_move(db, perm_ctx, "lead", lead, changes)
    await eenheid_ids_where(db, perm_ctx, "org:manage") -> set | None
    await visibility(db, perm_ctx) -> (OrgContext, InitiatiefContext)
    await perm_ctx_for(db, person_id) -> PermissionContext
    await prefetch(db, perm_ctx, "lead", lead_ids)  # bulk-locate, optional
    rights_on_eenheid(...), write_eenheid_ids(...), RESOURCE_TYPES

``require`` raises 401 (not logged in), 404 or 403.  404 when the resource
is missing and whenever the caller may not see it: a refused ``*:read``,
and a refused write on something they cannot read (that something exists
is information too).  403 only for a refused write on something visible.

Creating or moving something: pass where it will live.  Either
``eenheid_id=`` (the eenheid it goes into) or ``place=`` (the new record
or a dict with its placing fields, e.g. ``{"initiatief_id": ...}`` for a
lead, ``{"node_id": ..., "organisatie_eenheid_id": ...}`` for a task,
``{"opdrachtgever_id": ..., "opdrachtnemer_eenheid_id": ...}`` for an
opdracht, ``{"from_node_id": ..., "to_node_id": ...}`` for an edge).  The
place is located exactly like an existing resource of that type, so a
new task on a node is decided on the node like an existing one.  A child
permission can also be asked on its parent
(``require(db, ctx, "edge:create", "corpus_node", node_id)``): it is
decided as write access on that parent.  A new opdracht lands in every
eenheid it names, so creating one needs the permission in each of them.
A new eenheid below a parent is decided on that parent: ``org:create``
held there (a role on it or above it, or the eigenaar role of an external
organisation on it or above it).  A new root is free for an external type
(a gemeente, a stichting) for whoever holds ``org:create`` somewhere.  The
internal organisation only grows inside itself: an internal type only below
an internal parent; a ministerie, an internal root and an internal eenheid
below an external one only by super_admin (retyping and moving alike).
Moving an existing lead, task or
opdracht is :func:`require_move`: taking it away where it is and adding it
where it goes; moving an eenheid is ``core.authority``.

Rules of the model: seeing never implies writing, writing always implies
seeing, and a permission only counts where it holds.  ``core.org_context``
and ``core.initiatief_context`` build the visibility (members of the
internal organisation read up its line, members of an external eenheid see
that eenheid only; shares, resource roles); this module asks them for
reads.
``core.authority`` builds on it for decisions about grants.

One deliberate exception to read visibility: exporting the corpus and its
edges (``import_export:export``) is a platform operation for system roles
(platform_admin), like ``database:backup``, and reads everything.

Membership: "placed in an eenheid" below always means a *trusted*
placement (``repositories.org_tree.membership_ids_select``, the one
definition).  A placement is trusted when someone with authority over the
members of the eenheid (``core.authority.can_confirm_members``) made or
approved it (bron ``leidinggevende``) or an
official sync brought it (``TRUSTED_PLACEMENT_BRONNEN``: TK, kabinet, ABD,
ROO).  Contact administration (bron ``handmatig``, anyone with
``people:update``) and a manager's detachering of own staff into an
external organisation (bron ``detachering``) are informational: they show
who works where, but give no visibility, no implicit viewer role and no
share of a resource role or share held by the eenheid.  Moving an eenheid
never confirms the placements in it; bringing it into the organisation (a
move or a retype) or merging it takes the trust away that an eigenaar gave
(``core.authority.bring_into_organisation``, ``merge_into``).  Roles
(``PersonRole``) are separate grants and are not affected.  The implicit
viewer role (people directory, samenwerkingsverbanden, parlementair items)
only comes with membership of an eenheid that touches the internal
organisation (``org_tree.get_touching_ids``): an external root is anyone's
to create and staff, so its members only get what is granted or shared to
it.

Resolution order (first match wins; every step can only allow):

0. Reads are visibility, not rights.  ``<type>:read`` on a corpus_node,
   task, opdracht, initiatief, lead or a delegated sub-record is answered
   from the caller's visibility, the rule lists apply too:

   - corpus_node, task, opdracht: visible when one of its eenheden is
     visible in the org chart (an opdracht has two: opdrachtgever and
     opdrachtnemer), when it has no eenheid, or (a task without eenheid)
     when its node is visible.  Also when the caller holds a resource role
     on it that grants reading (step 2 roles; so a role that lets you
     write lets you see), a node shared with one of their eenheden (read or
     edit share), and a task assigned to them.
   - initiatief, lead: ``core.initiatief_context``.
   - an edge: when both nodes are visible; another sub-record: when a
     parent is.

   The corpus is not tenant-wide readable: reading follows org visibility.
   Only *writing* a node without eenheid is tenant-wide (step 5).  The row
   rules live in ``core.org_context`` next to their SQL form (the list
   filters), so a list, a detail and ``can`` answer alike.
   The modules that can be switched off per eenheid and are gated as a
   whole (``_MODULE_GATED``: tasks, opdrachten) also need their
   ``<type>:read`` somewhere, for reading and writing alike (only a
   resource role on the resource itself still counts without it, and the
   assignee still reads their own task); the list filters apply the same
   gate.  Nodes, initiatieven and leads have no
   such gate: their readers include people who only hold a resource role.
1. super_admin, or *permission* from a system-level role.  Synced eenheden
   (``bron`` other than ``handmatig``: TOOI, scrapes) are read-only for
   everyone but super_admin.
2. A resource role on the resource itself (``ResourcePermission``, direct or
   through an eenheid the person is placed in), mapped through
   ``RESOURCE_ROLE_PERMISSIONS``.  An eenheid's eigenaar role is a role on
   an eenheid and applies below it like any other: it counts on the
   eenheid, on everything below it, and for a new eenheid below them.
3. Parent delegation (``_DELEGATIONS`` below): the resource's rights come
   from its parent.  The permission is translated to the parent's domain:
   ``read`` stays ``read``, ``create``/``update`` become ``update``,
   ``delete`` becomes the parent verb named in the table.
4. *permission* held on the resource's eenheid (or on one above it: a role
   applies to everything below it), see ``rights_on_eenheid``.  For
   ``corpus_node`` and ``task`` an active *edit* share of that eenheid (or
   node) to an eenheid you are placed in counts as well, with the rights you
   hold there.  Read shares only give visibility.
5. Tenant-wide fallback, only for the types in ``_TENANT_WIDE_WHEN_UNSCOPED``
   and only when the resource has no eenheid and no parent: *permission*
   held through any role, anywhere.  Creating a new external root
   organisatie_eenheid is free in the same way (a stakeholder at the top;
   naming a manager is a grant decided by ``core.authority``).

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
suggested_edge         corpus_node of the parlementair item  (see below)
suggested_lead         initiatief                            initiatief:update
====================== ===================================== ==============

Suggestions: reviewing a suggested edge (approve, reject, reset, delete)
is the reviewer's mandate, ``parlementair:review`` on the node of the
parlementair item it belongs to (anywhere, when the item has no node yet).
Approving creates the edge under that same mandate: it is not asked as
``edge:create``, so a reviewer who edits no nodes still approves, and
editing the target end gives no say over the item.  Reviewing a suggested
lead (approve or reject) is ``initiatief:update``.

Edges: an edge is a relation of both nodes, so the editors of either end may
maintain it; the other end must be visible.  Sub-records without an RBAC
permission of their own use ``"<type>:<verb>"`` (``"lead_column:update"``)
and are decided entirely by their parent.

Tenant-wide fallbacks (step 5):

=========== ==============================================================
corpus_node Product decision: a node with an eenheid is written by rights
            on that eenheid; a node without one by anyone holding the
            permission through any role.  (Reading follows step 0.)
lead        A lead without initiatief and without eenheid (leads from
            before initiatieven existed).  A lead with an eenheid and no
            initiatief lives in that eenheid, for reading too.  Creating
            a new one without either is system-only: ``POST /leads`` puts
            it in the caller's own eenheid (``own_eenheid_where``).
opdracht    Same rule as the corpus: FCC imports mostly arrive without
            opdrachtgever or opdrachtnemer-eenheid.  With one of those, only
            rights on that eenheid count.
samenwerkingsverband
            Samenwerkingsverbanden are ad-hoc cross-organisation groups
            without an eenheid.  Their members are asked as
            ``samenwerkingsverband:update`` on the group itself.
tag         Tags are one shared vocabulary without an eenheid.
parlementair_item
            Imported parliamentary items: ``parlementair:read`` anywhere.
person      Creating a person or contact (``people:create``, no id).  An
            existing person is not decided here: editing, placing and
            deleting go through the ``core.authority`` guards.
=========== ==============================================================

Accepted behaviour (product decisions, not gaps):

- Work already assigned to an agent keeps receiving updates (comments,
  status, a new deadline) from whoever may edit it: only *handing* an agent
  work or power is super_admin's (``services.agent_rules``).
- ``GET /api/organisatie/{id}/personen`` is the tenant-wide staff
  directory by design: every logged-in user sees who is placed where
  (naam and functie; the full records only with ``people:read``).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.core.resource_roles import RESOURCE_ROLE_PERMISSIONS
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.github_link import GitHubLink
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import (
    INTERNAL_EENHEID_TYPES,
    OrganisatieEenheid,
)
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.models.tag import Tag
from bouwmeester.models.task import Task
from bouwmeester.repositories.org_tree import (
    get_chains,
    get_internal_ids,
    get_membership_ids,
    get_self_and_ancestor_ids,
    get_subtree_ids,
)
from bouwmeester.repositories.resource_permission import ResourcePermissionRepository
from bouwmeester.repositories.shared_access import share_active_today

if TYPE_CHECKING:
    from bouwmeester.core.initiatief_context import InitiatiefContext
    from bouwmeester.core.org_context import OrgContext

_NOT_LOGGED_IN = "Niet ingelogd"
_NOT_FOUND = "Niet gevonden"

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


async def _prefetch_chains(
    db: AsyncSession, perm_ctx: PermissionContext, eenheid_ids: Iterable[UUID]
) -> None:
    """Load the ancestor chains of many eenheden in one query (see ``_chain``)."""
    cache = perm_ctx.authz_cache
    missing = list({eid for eid in eenheid_ids if ("chain", eid) not in cache})
    for eid, chain in (await get_chains(db, missing)).items():
        cache[("chain", eid)] = chain


async def self_and_ancestor_ids(
    db: AsyncSession, perm_ctx: PermissionContext, eenheid_ids: Iterable[UUID]
) -> set[UUID]:
    """The eenheden plus every eenheid above them, from the request's chains."""
    eenheid_ids = list(eenheid_ids)
    await _prefetch_chains(db, perm_ctx, eenheid_ids)
    result: set[UUID] = set()
    for eid in eenheid_ids:
        result |= await _chain(db, perm_ctx, eid)
    return result


async def memberships(db: AsyncSession, perm_ctx: PermissionContext) -> list[UUID]:
    """The caller's memberships today (trusted placements), once per request."""
    key = ("memberships",)
    if key not in perm_ctx.authz_cache:
        perm_ctx.authz_cache[key] = (
            await get_membership_ids(db, perm_ctx.person_id)
            if perm_ctx.person_id
            else []
        )
    return perm_ctx.authz_cache[key]


# ---------------------------------------------------------------------------
# Where a resource lives: the one locator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Location:
    eenheid_ids: tuple[UUID, ...] = ()
    # (parent type, parent id); a None id is "no parent record yet", which
    # is decided like creating that parent without an eenheid.
    parents: tuple[tuple[str, UUID | None], ...] = ()
    node_id: UUID | None = None  # the node itself, for node shares
    # Only super_admin writes: a synced eenheid, or a new eenheid only
    # super_admin may create (a ministerie, see ``_place_eenheid``).
    read_only: bool = False
    assignee_id: UUID | None = None  # a task's assignee, who always reads it
    # A new resource that may go anywhere: the permission anywhere decides
    # (a new external root organisatie_eenheid).
    free_create: bool = False


# A locator finds many resources of one type in one query.
_Locator = Callable[
    [AsyncSession, dict, list[UUID]], Awaitable[dict[UUID, "_Location"]]
]
# A place locator builds the location of a resource that does not exist yet.
_PlaceLocator = Callable[[AsyncSession, dict, Any], Awaitable["_Location"]]


def _rows(model: Any, *columns: Any, where: Any = None) -> Callable:
    """A locator helper: ``{id: row}`` for the given ids, in one query."""

    async def fetch(db: AsyncSession, ids: list[UUID]) -> dict[UUID, Any]:
        stmt = select(model.id, *columns).where(model.id.in_(ids))
        if where is not None:
            stmt = stmt.where(where)
        return {row[0]: row[1:] for row in (await db.execute(stmt)).all()}

    return fetch


def _locator(fetch: Callable, build: Callable[[UUID, Any], _Location]) -> _Locator:
    async def locate(
        db: AsyncSession, cache: dict, ids: list[UUID]
    ) -> dict[UUID, _Location]:
        return {rid: build(rid, row) for rid, row in (await fetch(db, ids)).items()}

    return locate


def _eenheden(*ids: UUID | None) -> tuple[UUID, ...]:
    return tuple(eid for eid in ids if eid is not None)


def _parent_column(model: Any, parent_type: str, column: Any) -> _Locator:
    return _locator(
        _rows(model, column),
        lambda rid, row: _Location(parents=((parent_type, row[0]),) if row[0] else ()),
    )


def _scope_columns(model: Any) -> _Locator:
    return _locator(
        _rows(model, model.scope_type, model.scope_id),
        lambda rid, row: _Location(parents=((str(row[0]), row[1]),)),
    )


def _node_location(rid: UUID | None, eenheid_id: UUID | None) -> _Location:
    return _Location(eenheid_ids=_eenheden(eenheid_id), node_id=rid)


def _task_location(
    node_id: UUID | None, eenheid_id: UUID | None, assignee_id: UUID | None = None
) -> _Location:
    # A team's task is its team's; a task without eenheid is its node's.
    if eenheid_id is not None:
        return _Location(eenheid_ids=(eenheid_id,), assignee_id=assignee_id)
    return _Location(
        parents=(("corpus_node", node_id),) if node_id else (),
        assignee_id=assignee_id,
    )


async def _place_eenheid(db: AsyncSession, cache: dict, place: Any) -> _Location:
    """Where a new eenheid goes: below its parent, or at the top.

    Below a parent it lives in that parent, so ``org:create`` held on the
    parent decides (a role there or above it, or an eenheid's eigenaar role
    there or above it).  A new external root (a gemeente, a stichting) is
    free: ``org:create`` held anywhere suffices.

    The internal organisation only grows inside itself: an internal type
    goes below an internal parent, where ``org:create`` decides as above.
    A ministerie (its top), an internal root and an internal eenheid below
    an external one are super_admin's (``read_only``).  Retyping or moving
    an eenheid asks the same (``core.authority.require_can_move_eenheid``).
    """
    parent_id = _field(place, "parent_id")
    eenheid_type = _field(place, "type")
    if eenheid_type in INTERNAL_EENHEID_TYPES and (
        eenheid_type == "ministerie"
        or parent_id is None
        or not await get_internal_ids(db, [parent_id])
    ):
        return _Location(read_only=True)
    if parent_id is not None:
        return _Location(eenheid_ids=(parent_id,))
    return _Location(free_create=True)


def _is_assignee(perm_ctx: PermissionContext, loc: _Location) -> bool:
    return loc.assignee_id is not None and loc.assignee_id == perm_ctx.person_id


def _synced(bron: str | None) -> bool:
    return bron is not None and bron != "handmatig"


async def _locate_initiatieven(
    db: AsyncSession, cache: dict, ids: list[UUID]
) -> dict[UUID, _Location]:
    """An initiatief lives in the eenheden linked to it as eigenaar."""
    found = (
        await db.scalars(select(Initiatief.id).where(Initiatief.id.in_(ids)))
    ).all()
    owners: dict[UUID, list[UUID]] = {rid: [] for rid in found}
    rows = await db.execute(
        select(
            ResourcePermission.resource_id, ResourcePermission.organisatie_eenheid_id
        ).where(
            ResourcePermission.resource_type == "initiatief",
            ResourcePermission.resource_id.in_(found),
            ResourcePermission.rol == "eigenaar",
            ResourcePermission.organisatie_eenheid_id.isnot(None),
        )
    )
    for rid, eid in rows.all():
        owners[rid].append(eid)
    return {rid: _Location(eenheid_ids=tuple(sorted(e))) for rid, e in owners.items()}


async def _lead_location(
    db: AsyncSession, cache: dict, initiatief_id: UUID | None, eenheid_id: UUID | None
) -> _Location:
    if initiatief_id is None:
        return _Location(eenheid_ids=_eenheden(eenheid_id))
    # A lead in an initiatief lives in the initiatief's owner eenheden.
    initiatief = await _locate(db, cache, "initiatief", initiatief_id)
    return _Location(
        eenheid_ids=initiatief.eenheid_ids if initiatief else (),
        parents=(("initiatief", initiatief_id),),
    )


async def _locate_leads(
    db: AsyncSession, cache: dict, ids: list[UUID]
) -> dict[UUID, _Location]:
    rows = await _rows(Lead, Lead.initiatief_id, Lead.organisatie_eenheid_id)(db, ids)
    await _locate_many(
        db, cache, "initiatief", [r[0] for r in rows.values() if r[0] is not None]
    )
    return {rid: await _lead_location(db, cache, *row) for rid, row in rows.items()}


def _suggested_edge_location(rid: UUID, row: Any) -> _Location:
    # Reviewing is the mandate of whoever reviews the item's node.
    return _Location(parents=(("corpus_node", row[0]),))


# Types that live in an eenheid or under a parent.
_LOCATORS: dict[str, _Locator] = {
    "corpus_node": _locator(
        _rows(CorpusNode, CorpusNode.organisatie_eenheid_id),
        lambda rid, row: _node_location(rid, row[0]),
    ),
    "organisatie_eenheid": _locator(
        _rows(OrganisatieEenheid, OrganisatieEenheid.bron),
        lambda rid, row: _Location(eenheid_ids=(rid,), read_only=_synced(row[0])),
    ),
    # The client and the team doing the work both answer for an opdracht.
    "opdracht": _locator(
        _rows(Opdracht, Opdracht.opdrachtgever_id, Opdracht.opdrachtnemer_eenheid_id),
        lambda rid, row: _Location(eenheid_ids=_eenheden(*row)),
    ),
    "initiatief": _locate_initiatieven,
    "task": _locator(
        _rows(Task, Task.node_id, Task.organisatie_eenheid_id, Task.assignee_id),
        lambda rid, row: _task_location(*row),
    ),
    "lead": _locate_leads,
    "edge": _locator(
        _rows(Edge, Edge.from_node_id, Edge.to_node_id),
        lambda rid, row: _Location(
            parents=(("corpus_node", row[0]), ("corpus_node", row[1]))
        ),
    ),
    "initiatief_update": _parent_column(
        InitiatiefUpdatePost, "initiatief", InitiatiefUpdatePost.initiatief_id
    ),
    "lead_column": _parent_column(LeadColumn, "initiatief", LeadColumn.initiatief_id),
    "lead_update": _parent_column(LeadUpdatePost, "lead", LeadUpdatePost.lead_id),
    "lead_activity": _parent_column(LeadActivity, "lead", LeadActivity.lead_id),
    "lead_attachment": _parent_column(LeadAttachment, "lead", LeadAttachment.lead_id),
    "parlementair_abonnement": _scope_columns(ParlementairAbonnement),
    "mattermost_channel_link": _scope_columns(MattermostChannelLink),
    "github_link": _scope_columns(GitHubLink),
    "stakeholder_assessment": _scope_columns(StakeholderAssessment),
    "suggested_edge": _locator(
        _rows(
            SuggestedEdge,
            ParlementairItem.corpus_node_id,
            where=ParlementairItem.id == SuggestedEdge.parlementair_item_id,
        ),
        _suggested_edge_location,
    ),
    "suggested_lead": _parent_column(
        SuggestedLead, "initiatief", SuggestedLead.initiatief_id
    ),
}

# Types that live nowhere in particular: only their existence is looked up.
for _type, _model in {
    "samenwerkingsverband": Samenwerkingsverband,
    "tag": Tag,
    "parlementair_item": ParlementairItem,
}.items():
    _LOCATORS[_type] = _locator(_rows(_model), lambda rid, row: _Location())


def _field(place: Any, name: str) -> Any:
    if isinstance(place, dict):
        return place.get(name)
    return getattr(place, name, None)


async def _place_lead(db: AsyncSession, cache: dict, place: Any) -> _Location:
    return await _lead_location(
        db,
        cache,
        _field(place, "initiatief_id"),
        _field(place, "organisatie_eenheid_id"),
    )


def _sync_place(build: Callable[[Any], _Location]) -> _PlaceLocator:
    async def locate(db: AsyncSession, cache: dict, place: Any) -> _Location:
        return build(place)

    return locate


# Where a new resource of each type would live, from its placing fields.
_PLACES: dict[str, _PlaceLocator] = {
    "corpus_node": _sync_place(
        lambda p: _node_location(None, _field(p, "organisatie_eenheid_id"))
    ),
    "task": _sync_place(
        lambda p: _task_location(
            _field(p, "node_id"), _field(p, "organisatie_eenheid_id")
        )
    ),
    "lead": _place_lead,
    "organisatie_eenheid": _place_eenheid,
    "opdracht": _sync_place(
        lambda p: _Location(
            eenheid_ids=_eenheden(
                _field(p, "opdrachtgever_id"), _field(p, "opdrachtnemer_eenheid_id")
            )
        )
    ),
    "edge": _sync_place(
        lambda p: _Location(
            parents=tuple(
                ("corpus_node", nid)
                for nid in (_field(p, "from_node_id"), _field(p, "to_node_id"))
                if nid is not None
            )
        )
    ),
}


async def _locate_many(
    db: AsyncSession, cache: dict, resource_type: str, ids: Iterable[UUID]
) -> None:
    """Locate every id not located yet, in one query, into *cache*."""
    if resource_type not in _LOCATORS:
        if resource_type in _CREATE_ONLY_TYPES:
            raise ValueError(
                f"authz: an existing {resource_type} is decided by core.authority"
            )
        raise ValueError(f"authz: unknown resource type {resource_type!r}")
    missing = list({rid for rid in ids if ("loc", resource_type, rid) not in cache})
    if not missing:
        return
    found = await _LOCATORS[resource_type](db, cache, missing)
    for rid in missing:
        cache[("loc", resource_type, rid)] = found.get(rid)


async def _locate(
    db: AsyncSession, cache: dict, resource_type: str, rid: UUID
) -> _Location | None:
    await _locate_many(db, cache, resource_type, [rid])
    return cache[("loc", resource_type, rid)]


async def prefetch(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    ids: Iterable[UUID],
) -> None:
    """Locate many resources (and their parents) in one query per type.

    Optional: decisions locate what they need themselves.  Call this before
    deciding the same action on many resources (a board of leads, the edges
    of a node) so the decisions cost a constant number of queries.
    """
    ids = list(ids)
    cache = perm_ctx.authz_cache
    await _locate_many(db, cache, resource_type, ids)
    parents: dict[str, set[UUID]] = {}
    eenheden: set[UUID] = set()
    for rid in ids:
        loc = cache[("loc", resource_type, rid)]
        if loc is None:
            continue
        eenheden.update(loc.eenheid_ids)
        for parent_type, parent_id in loc.parents:
            if parent_id is not None:
                parents.setdefault(parent_type, set()).add(parent_id)
    await _prefetch_chains(db, perm_ctx, eenheden)
    for parent_type, parent_ids in parents.items():
        await prefetch(db, perm_ctx, parent_type, parent_ids)


async def get_eenheid_ids(
    db: AsyncSession, resource_type: str, resource_id: UUID
) -> tuple[bool, list[UUID]]:
    """``(found, eenheid_ids)``: where the resource lives (for ``core.authority``).

    The eenheden whose rights count for the resource itself; a resource that
    lives under a parent only (a task without eenheid) has none.
    """
    loc = await _locate(db, {}, resource_type, resource_id)
    return (loc is not None, list(loc.eenheid_ids) if loc else [])


# ---------------------------------------------------------------------------
# Delegation to parents
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Delegation:
    parent_types: tuple[str, ...]
    delete_verb: str = "update"
    # A write asks this permission on the parent instead of a translated verb.
    write_permission: str | None = None
    # Reading needs every parent (an edge), not any.
    read_needs_all_parents: bool = False


# The delegation table; see the module docstring for the same in prose.
_DELEGATIONS: dict[str, _Delegation] = {
    "edge": _Delegation(
        ("corpus_node",), delete_verb="delete", read_needs_all_parents=True
    ),
    "task": _Delegation(("corpus_node",)),
    "lead": _Delegation(("initiatief",), delete_verb="delete"),
    "initiatief_update": _Delegation(("initiatief",)),
    "lead_column": _Delegation(("initiatief",)),
    "lead_update": _Delegation(("lead",)),
    "lead_activity": _Delegation(("lead",)),
    "lead_attachment": _Delegation(("lead",)),
    "parlementair_abonnement": _Delegation(("initiatief", "lead")),
    "mattermost_channel_link": _Delegation(("initiatief", "lead")),
    "github_link": _Delegation(("initiatief", "lead")),
    "stakeholder_assessment": _Delegation(("corpus_node", "initiatief")),
    "suggested_edge": _Delegation(
        ("corpus_node",), write_permission="parlementair:review"
    ),
    "suggested_lead": _Delegation(("initiatief",)),
}

# Types decided here only when created; changing an existing one is a grant
# decision in ``core.authority`` (a person's emails are their identity).
_CREATE_ONLY_TYPES = frozenset({"person"})

_TENANT_WIDE_WHEN_UNSCOPED = frozenset(
    {
        "corpus_node",
        "lead",
        "opdracht",
        "parlementair_item",
        "person",
        "samenwerkingsverband",
        "tag",
    }
)

# A new one of these without a place lands in the caller's own eenheid
# (:func:`own_eenheid_where`); only system roles create one that lives
# nowhere in particular (step 1).
_CREATED_IN_OWN_EENHEID = frozenset({"lead"})

# Every resource type can() knows (for input validation by callers).
RESOURCE_TYPES = frozenset(set(_LOCATORS) | _CREATE_ONLY_TYPES)

# A new one of these lands in every eenheid it names (an opdracht in both
# its opdrachtgever and its opdrachtnemer-eenheid), so creating it needs
# the permission in each of them, not in one.
_CREATE_IN_EVERY_EENHEID = frozenset({"opdracht"})

# Types whose eenheid can be shared for editing (``SharedAccess``).
_SHAREABLE_TYPES = frozenset({"corpus_node", "task"})

# Read by visibility of the eenheden they live in (step 0).
_READ_BY_EENHEID = frozenset({"corpus_node", "task", "opdracht"})

# Types whose existence is hidden from whoever cannot read them (step 0).
_READ_BY_VISIBILITY = _READ_BY_EENHEID | {"initiatief", "lead"} | set(_DELEGATIONS)

# Modules whose routes are gated as a whole on ``<type>:read`` (a module
# toggle can take that permission away per eenheid).
_MODULE_GATED = frozenset({"task", "opdracht"})

# Permission prefix per resource type where they differ.
_PERM_DOMAIN = {
    "corpus_node": "node",
    "organisatie_eenheid": "org",
    "person": "people",
    "parlementair_item": "parlementair",
}
_DOMAIN_TYPE = {v: k for k, v in _PERM_DOMAIN.items()}


def _domain(resource_type: str) -> str:
    return _PERM_DOMAIN.get(resource_type, resource_type)


def readable_modules(perm_ctx: PermissionContext) -> frozenset[str]:
    """The switchable modules (``_MODULE_GATED``) the caller reads somewhere."""
    return frozenset(
        t for t in _MODULE_GATED if perm_ctx.has_permission(f"{_domain(t)}:read")
    )


async def role_read_ids(
    db: AsyncSession, perm_ctx: PermissionContext, resource_type: str
) -> list[UUID]:
    """The resources of one type the caller reads through a resource role.

    Step 2 for ``<type>:read``: a role held directly or through an eenheid
    the caller is placed in, that grants reading.  ``core.org_context``
    adds these to the visibility, so writing through a role implies seeing.
    """
    if perm_ctx.person_id is None:
        return []
    read = f"{_domain(resource_type)}:read"
    granting = {
        rol
        for rol, perms in RESOURCE_ROLE_PERMISSIONS.get(resource_type, {}).items()
        if read in perms
    }
    held = await _resource_roles(db, perm_ctx, resource_type)
    return [rid for rid, rols in held.items() if rols & granting]


def _parent_permission(
    permission: str, child_type: str, parent_type: str
) -> str | None:
    """Translate a child's permission to the one needed on its parent."""
    delegation = _DELEGATIONS[child_type]
    verb = permission.partition(":")[2]
    if verb == "read":
        parent_verb = "read"
    elif verb in ("create", "update", "delete") and delegation.write_permission:
        return delegation.write_permission
    elif verb in ("create", "update"):
        parent_verb = "update"
    elif verb == "delete":
        parent_verb = delegation.delete_verb
    else:
        return None
    return f"{_domain(parent_type)}:{parent_verb}"


def _child_type_of(permission: str, resource_type: str) -> str | None:
    """The child type when *permission* is about a child of *resource_type*."""
    domain = permission.partition(":")[0]
    child = _DOMAIN_TYPE.get(domain, domain)
    if child == resource_type or child not in _DELEGATIONS:
        return None
    return child if resource_type in _DELEGATIONS[child].parent_types else None


# ---------------------------------------------------------------------------
# Where someone can write (used by core.org_context for visibility)
# ---------------------------------------------------------------------------

_WRITE_VERBS = frozenset({"create", "update", "delete", "manage"})
_EENHEID_TYPES = frozenset(
    {"corpus_node", "initiatief", "opdracht", "organisatie_eenheid", "task", "lead"}
)


def _is_eenheid_write(permission: str) -> bool:
    """True if *permission* lets step 4 write something that lives in an eenheid."""
    domain, _, verb = permission.partition(":")
    resource_type = _DOMAIN_TYPE.get(domain, domain)
    located = resource_type in _EENHEID_TYPES or resource_type in _DELEGATIONS
    return verb in _WRITE_VERBS and located


def write_eenheid_ids(perm_ctx: PermissionContext) -> list[UUID]:
    """Eenheden where a scoped role lets the person write (and so below them).

    Rights inherit downward, so whoever can write in an eenheid must also
    see what lies below it; ``core.org_context`` makes those subtrees
    visible.  This includes every eenheid a manager manages.
    """
    return [
        eid
        for eid, perms in perm_ctx.scoped_permissions.items()
        if any(_is_eenheid_write(p) for p in perms)
    ]


# ---------------------------------------------------------------------------
# Visibility (step 0), built once per request
# ---------------------------------------------------------------------------


async def perm_ctx_for(db: AsyncSession, person_id: UUID | None) -> PermissionContext:
    """The PermissionContext of *person_id* (None or unknown: anonymous)."""
    from bouwmeester.core.permissions import (
        anonymous_permission_context,
        build_permission_context,
    )
    from bouwmeester.models.person import Person

    person = await db.get(Person, person_id) if person_id else None
    if person is None:
        return anonymous_permission_context()
    return await build_permission_context(db, person)


async def org_visibility(db: AsyncSession, perm_ctx: PermissionContext) -> OrgContext:
    """The caller's org visibility, built once per request."""
    from bouwmeester.core.org_context import build_org_context
    from bouwmeester.models.person import Person

    key = ("org_ctx",)
    if key not in perm_ctx.authz_cache:
        person = (
            await db.get(Person, perm_ctx.person_id) if perm_ctx.person_id else None
        )
        perm_ctx.authz_cache[key] = await build_org_context(
            db, person, perm_ctx=perm_ctx
        )
    return perm_ctx.authz_cache[key]


async def visibility(
    db: AsyncSession, perm_ctx: PermissionContext
) -> tuple[OrgContext, InitiatiefContext]:
    """The caller's org and initiatief visibility, built once per request."""
    from bouwmeester.core.initiatief_context import build_initiatief_context
    from bouwmeester.models.person import Person

    org_ctx = await org_visibility(db, perm_ctx)
    key = ("init_ctx",)
    if key not in perm_ctx.authz_cache:
        person = (
            await db.get(Person, perm_ctx.person_id) if perm_ctx.person_id else None
        )
        perm_ctx.authz_cache[key] = await build_initiatief_context(
            db, person, perm_ctx=perm_ctx, org_ctx=org_ctx
        )
    return org_ctx, perm_ctx.authz_cache[key]


async def _read_decision(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    resource_id: UUID | None,
    loc: _Location,
) -> bool | None:
    """The answer to ``<resource_type>:read``, or None when rights decide.

    The row forms of ``core.org_context`` / ``core.initiatief_context``, the
    same rules the list filters apply.
    """
    from bouwmeester.core.org_context import sees_node, sees_opdracht, sees_task

    if resource_type in ("initiatief", "lead"):
        if resource_id is None:
            return None
        _, init_ctx = await visibility(db, perm_ctx)
        if resource_type == "initiatief":
            return init_ctx.sees_initiatief(resource_id)
        initiatief_id = next((pid for _, pid in loc.parents), None)
        own_eenheid = None if initiatief_id else next(iter(loc.eenheid_ids), None)
        return init_ctx.sees_lead_in(resource_id, initiatief_id, own_eenheid)
    if resource_type in _READ_BY_EENHEID:
        org_ctx = await org_visibility(db, perm_ctx)
        if resource_type == "corpus_node":
            return sees_node(org_ctx, resource_id, next(iter(loc.eenheid_ids), None))
        if resource_type == "opdracht":
            return sees_opdracht(org_ctx, resource_id, loc.eenheid_ids)
        seen = sees_task(org_ctx, next(iter(loc.eenheid_ids), None), loc.assignee_id)
        if seen is not None:
            return seen
        # A task without eenheid is read through its node (below).
    if resource_type in _DELEGATIONS:
        if not loc.parents:
            return False
        reads = [
            bool(await _decide(db, perm_ctx, f"{_domain(pt)}:read", pt, pid, None))
            for pt, pid in loc.parents
            if pid is not None
        ]
        delegation = _DELEGATIONS.get(resource_type)
        if delegation is not None and delegation.read_needs_all_parents:
            return bool(reads) and all(reads)
        return any(reads)
    return None


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


async def _resource_roles(
    db: AsyncSession, perm_ctx: PermissionContext, resource_type: str
) -> dict[UUID, set[str]]:
    """The caller's resource roles on every resource of one type.

    One query per type per request, so deciding N leads (a reorder) does not
    cost N queries.  Like the decisions themselves, a grant made later in
    the same request is not seen.
    """
    key = ("resource_roles", resource_type)
    if key not in perm_ctx.authz_cache:
        assert perm_ctx.person_id is not None
        perm_ctx.authz_cache[key] = await ResourcePermissionRepository(
            db
        ).get_roles_for_person_by_resource(perm_ctx.person_id, resource_type)
    return perm_ctx.authz_cache[key]


async def _holds_resource_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None,
) -> bool:
    """Step 2: a resource role of the caller on the resource grants *permission*."""
    role_perms = RESOURCE_ROLE_PERMISSIONS.get(resource_type, {})
    if (
        resource_id is None
        or perm_ctx.person_id is None
        or not any(permission in granted for granted in role_perms.values())
    ):
        return False
    held = await _resource_roles(db, perm_ctx, resource_type)
    return any(permission in role_perms.get(r, ()) for r in held.get(resource_id, ()))


async def _holds_eenheid_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    eenheid_ids: Iterable[UUID],
) -> bool:
    """Step 2 for eenheden: an eenheid role (eigenaar) on it or above it.

    A role on an eenheid applies below it, so the eigenaar of an external
    organisation maintains what hangs below it and creates there.
    """
    if perm_ctx.person_id is None:
        return False
    role_perms = RESOURCE_ROLE_PERMISSIONS["organisatie_eenheid"]
    held = await _resource_roles(db, perm_ctx, "organisatie_eenheid")
    granted = {
        eid
        for eid, rols in held.items()
        if any(permission in role_perms.get(rol, ()) for rol in rols)
    }
    if not granted:
        return False
    for eid in eenheid_ids:
        if await _chain(db, perm_ctx, eid) & granted:
            return True
    return False


async def _holds_on_eenheden(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    eenheid_ids: Iterable[UUID],
) -> bool:
    for eid in eenheid_ids:
        if (await rights_on_eenheid(db, perm_ctx, eid)).has(permission):
            return True
    return False


async def _edit_shares(
    db: AsyncSession, perm_ctx: PermissionContext
) -> list[tuple[UUID | None, UUID | None, UUID]]:
    """Active edit shares to eenheden the caller is placed in, once per request."""
    key = ("edit_shares",)
    if key not in perm_ctx.authz_cache:
        own = await memberships(db, perm_ctx)
        rows = []
        if own:
            rows = (
                await db.execute(
                    select(
                        SharedAccess.source_eenheid_id,
                        SharedAccess.source_node_id,
                        SharedAccess.target_eenheid_id,
                    ).where(
                        SharedAccess.target_eenheid_id.in_(own),
                        SharedAccess.access_level == "edit",
                        share_active_today(),
                    )
                )
            ).all()
        perm_ctx.authz_cache[key] = [tuple(row) for row in rows]
    return perm_ctx.authz_cache[key]


async def _holds_via_edit_share(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    loc: _Location,
) -> bool:
    """Step 4b: an edit share lets a target eenheid work with its own rights."""
    targets = {
        target
        for source_eenheid, source_node, target in await _edit_shares(db, perm_ctx)
        if source_eenheid in loc.eenheid_ids
        or (loc.node_id is not None and source_node == loc.node_id)
    }
    return await _holds_on_eenheden(db, perm_ctx, permission, targets)


async def _decide(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None,
    place: _Location | None,
) -> bool | None:
    """True/False, or None when the resource does not exist."""
    key = ("decision", permission, resource_type, resource_id, place)
    if key in perm_ctx.authz_cache:
        return perm_ctx.authz_cache[key]
    result = await _resolve(db, perm_ctx, permission, resource_type, resource_id, place)
    perm_ctx.authz_cache[key] = result
    return result


async def _resolve(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None,
    place: _Location | None,
) -> bool | None:
    if resource_id is None:
        loc = place or _Location()
    else:
        found = await _locate(db, perm_ctx.authz_cache, resource_type, resource_id)
        if found is None:
            return None
        loc = found
    domain, _, verb = permission.partition(":")
    own_domain = domain == _domain(resource_type)

    # A switched-off module is off for reading and writing alike, so what
    # you may write you can also see.  Only a resource role on the resource
    # itself (an opdracht eigenaar) still counts, for both, and the assignee
    # still reads their own task (``sees_task``).
    if (
        own_domain
        and resource_type in _MODULE_GATED
        and resource_type not in readable_modules(perm_ctx)
    ):
        if verb == "read" and _is_assignee(perm_ctx, loc):
            return True
        return await _holds_resource_role(
            db, perm_ctx, permission, resource_type, resource_id
        )

    # 0. Reading is seeing.
    if own_domain and verb == "read":
        decision = await _read_decision(db, perm_ctx, resource_type, resource_id, loc)
        if decision is not None:
            return decision

    # Synced eenheden belong to their sync.
    if own_domain and verb != "read" and loc.read_only and not perm_ctx.is_super_admin:
        return False

    # 1. System level.
    if perm_ctx.has_system_permission(permission):
        return True

    # A child's permission asked on its parent ("edge:create" on a node) is
    # the translated permission on that parent.
    child = _child_type_of(permission, resource_type)
    if child is not None:
        parent_perm = _parent_permission(permission, child, resource_type)
        if parent_perm is None:
            return False
        return bool(
            await _decide(db, perm_ctx, parent_perm, resource_type, resource_id, place)
        )

    # 2. A resource role on the resource itself (an eenheid role: or above it).
    if resource_type == "organisatie_eenheid":
        if await _holds_eenheid_role(db, perm_ctx, permission, loc.eenheid_ids):
            return True
    elif await _holds_resource_role(
        db, perm_ctx, permission, resource_type, resource_id
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
    if (
        resource_id is None
        and verb == "create"
        and resource_type in _CREATE_IN_EVERY_EENHEID
        and loc.eenheid_ids
    ):
        return all(
            [
                await _holds_on_eenheden(db, perm_ctx, permission, [eid])
                for eid in loc.eenheid_ids
            ]
        )
    if await _holds_on_eenheden(db, perm_ctx, permission, loc.eenheid_ids):
        return True
    if (
        resource_type in _SHAREABLE_TYPES
        and (loc.eenheid_ids or loc.node_id)
        and await _holds_via_edit_share(db, perm_ctx, permission, loc)
    ):
        return True

    # 5. Tenant-wide fallback for resources that live nowhere in particular.
    unscoped = not loc.eenheid_ids and not loc.parents
    if (
        unscoped
        and resource_type in _TENANT_WIDE_WHEN_UNSCOPED
        and not (resource_id is None and resource_type in _CREATED_IN_OWN_EENHEID)
    ):
        return perm_ctx.has_permission(permission)
    return (
        resource_id is None
        and verb == "create"
        and loc.free_create
        and perm_ctx.has_permission(permission)
    )


async def _place_location(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    eenheid_id: UUID | None,
    place: Any,
) -> _Location | None:
    if place is not None:
        if resource_type not in _PLACES:
            raise ValueError(f"authz: no place locator for {resource_type!r}")
        return await _PLACES[resource_type](db, perm_ctx.authz_cache, place)
    return _Location(eenheid_ids=(eenheid_id,)) if eenheid_id else None


async def can(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None = None,
    *,
    eenheid_id: UUID | None = None,
    place: Any = None,
) -> bool:
    """May *perm_ctx* do *permission* on this resource?

    Pass ``resource_id`` for an existing resource, or ``eenheid_id`` /
    ``place`` (or nothing) for one about to be created or moved there.  A
    missing resource is ``False``.
    """
    if not perm_ctx.is_authenticated:
        return False
    loc = await _place_location(db, perm_ctx, resource_type, eenheid_id, place)
    return bool(
        await _decide(db, perm_ctx, permission, resource_type, resource_id, loc)
    )


async def _holds_parent_role_for(
    db: AsyncSession, perm_ctx: PermissionContext, permission: str, resource_type: str
) -> bool:
    """A resource role on some parent that lets the caller create this child."""
    if perm_ctx.person_id is None or resource_type not in _DELEGATIONS:
        return False
    for parent_type in _DELEGATIONS[resource_type].parent_types:
        parent_perm = _parent_permission(permission, resource_type, parent_type)
        role_perms = RESOURCE_ROLE_PERMISSIONS.get(parent_type, {})
        held = await _resource_roles(db, perm_ctx, parent_type)
        if any(
            parent_perm in role_perms.get(rol, ())
            for rols in held.values()
            for rol in rols
        ):
            return True
    return False


async def can_anywhere(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
) -> bool:
    """Is there any place where *perm_ctx* may create this new resource?

    For generic create buttons (a task, a lead).  Asks :func:`can` for "no
    eenheid" (system roles, tenant-wide fallback), for every eenheid the
    person holds a scoped role on (a role applies below it, so those are
    where it holds first), and whether a resource role on some parent (an
    initiatief contributor, a node eigenaar) lets them create it there.

    A lead is created without a place in the caller's own eenheid
    (``_CREATED_IN_OWN_EENHEID``), so for a lead this asks exactly what
    ``POST /api/leads`` without initiatief and eenheid allows: a system
    role, or an own eenheid where creating holds.  Creating one in an
    initiatief is ``lead:create`` on that initiatief.
    """
    if await can(db, perm_ctx, permission, resource_type):
        return True
    if resource_type in _CREATED_IN_OWN_EENHEID:
        own = await own_eenheid_where(db, perm_ctx, permission, resource_type)
        return own is not None
    for eenheid_id in perm_ctx.scoped_permissions:
        if await can(db, perm_ctx, permission, resource_type, eenheid_id=eenheid_id):
            return True
    return await _holds_parent_role_for(db, perm_ctx, permission, resource_type)


async def own_eenheid_where(
    db: AsyncSession, perm_ctx: PermissionContext, permission: str, resource_type: str
) -> UUID | None:
    """The first of the caller's own eenheden where a new resource may go.

    Own eenheden are the trusted, active placements, longest-running first
    (``get_membership_ids``), so asking and creating, over REST or chat,
    pick the same one.  ``None`` when there is none.
    """
    for eenheid_id in await memberships(db, perm_ctx):
        if await can(db, perm_ctx, permission, resource_type, eenheid_id=eenheid_id):
            return eenheid_id
    return None


async def eenheid_ids_where(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    *,
    eenheid_type: str | None = None,
) -> set[UUID] | None:
    """The eenheden where ``can`` allows an ``org:*`` *permission*; None: all.

    ``org:update`` / ``org:manage`` are asked on the eenheid itself,
    ``org:create`` as creating an eenheid (of *eenheid_type*) below it.
    Candidates are the subtrees of the eenheden where a scoped role or an
    eenheid role (eigenaar) grants the permission (both apply below them);
    each is then decided by :func:`can`, so this list and the decisions
    agree.  A new root is no eenheid and is asked through ``can``.  A
    system role holds everywhere (None), except for creating an internal
    type, which only goes below an internal eenheid (``_place_eenheid``).
    """
    internal_create = (
        permission.endswith(":create") and eenheid_type in INTERNAL_EENHEID_TYPES
    )
    if perm_ctx.is_super_admin or (
        perm_ctx.has_system_permission(permission) and not internal_create
    ):
        return None
    roots = {
        eid for eid, perms in perm_ctx.scoped_permissions.items() if permission in perms
    }
    if perm_ctx.has_system_permission(permission):
        roots |= set(
            (
                await db.scalars(
                    select(OrganisatieEenheid.id).where(
                        OrganisatieEenheid.type.in_(INTERNAL_EENHEID_TYPES)
                    )
                )
            ).all()
        )
    if perm_ctx.person_id is not None:
        granting = RESOURCE_ROLE_PERMISSIONS["organisatie_eenheid"]
        for eid, rols in (
            await _resource_roles(db, perm_ctx, "organisatie_eenheid")
        ).items():
            if any(permission in granting.get(rol, ()) for rol in rols):
                roots.add(eid)
    candidates = await get_subtree_ids(db, list(roots))
    await prefetch(db, perm_ctx, "organisatie_eenheid", candidates)
    allowed = set()
    for eid in candidates:
        if permission.endswith(":create"):
            place = {"parent_id": eid, "type": eenheid_type}
            ok = await can(db, perm_ctx, permission, "organisatie_eenheid", place=place)
        else:
            ok = await can(db, perm_ctx, permission, "organisatie_eenheid", eid)
        if ok:
            allowed.add(eid)
    return allowed


async def require(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    permission: str,
    resource_type: str,
    resource_id: UUID | None = None,
    *,
    eenheid_id: UUID | None = None,
    place: Any = None,
) -> None:
    """Like :func:`can`, but raises 401, 404 or 403.

    404 when the resource does not exist, and whenever the caller may not
    read it: a refused ``*:read``, and a refused write on something they
    cannot see (that something exists is information too).  403 only for
    a refused write on something they can see.
    """
    if not perm_ctx.is_authenticated:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _NOT_LOGGED_IN)
    loc = await _place_location(db, perm_ctx, resource_type, eenheid_id, place)
    decision = await _decide(db, perm_ctx, permission, resource_type, resource_id, loc)
    if decision is None or (
        not decision
        and (
            permission.endswith(":read")
            or not await _readable(db, perm_ctx, resource_type, resource_id)
        )
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    if not decision:
        located = perm_ctx.authz_cache.get(("loc", resource_type, resource_id))
        if located is not None and located.read_only:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Deze organisatie-eenheid is read-only: TOOI-, scrape- en "
                "synthetische eenheden worden door de sync beheerd, alleen "
                "super_admin wijzigt ze handmatig",
            )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Je hebt hier geen rechten voor: je rechten gelden alleen binnen je "
            "eigen organisatie-eenheden en de items waar je een rol op hebt",
        )


# The fields that say where a resource lives, per type that can move.
_PLACING_FIELDS: dict[str, tuple[str, ...]] = {
    "lead": ("initiatief_id", "organisatie_eenheid_id"),
    "task": ("node_id", "organisatie_eenheid_id"),
    "opdracht": ("opdrachtgever_id", "opdrachtnemer_eenheid_id"),
}


async def require_move(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    record: Any,
    changes: dict[str, Any],
) -> None:
    """Guard changing where an existing lead, task or opdracht lives.

    *record* is the resource as it is; *changes* holds the fields of the
    update (only those sent), of which the placing fields count.  Moving is
    taking it away where it is and adding it where it goes:

    - lead: every move takes it away from its old home, so it needs
      ``lead:delete`` on the lead and ``lead:create`` at the new place
      (another initiatief, another eenheid, or from an eenheid into an
      initiatief, one's own new initiatief included).  Otherwise moving
      would turn ``lead:update`` into deleting it where it was.  A lead in
      an initiatief never goes back to no initiatief (422); its
      ``organisatie_eenheid_id`` is only a label there (the initiatief
      decides), so changing it is a plain update.  Clearing the eenheid of
      a lead without initiatief makes it tenant-wide, which only system
      roles may do.
    - task: ``task:update`` on the task and ``task:create`` at the new place.
    - opdracht: ``opdracht:update`` on every eenheid that changes, the one it
      leaves and the one it lands in; taking all its eenheden away makes it
      tenant-wide, which only system roles may do.
    """
    fields = _PLACING_FIELDS[resource_type]
    old = {f: getattr(record, f) for f in fields}
    new = {f: changes.get(f, old[f]) for f in fields}
    if new == old:
        return
    if resource_type == "opdracht":
        await _require_opdracht_move(db, perm_ctx, old, new)
        return
    old_initiatief = old.get("initiatief_id")
    if resource_type == "lead" and old_initiatief is not None:
        if new["initiatief_id"] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Een lead in een initiatief kan niet meer zonder initiatief",
            )
        if new["initiatief_id"] == old_initiatief:
            return
    take_away = "lead:delete" if resource_type == "lead" else f"{resource_type}:update"
    if (
        resource_type == "lead"
        and new["initiatief_id"] is None
        and new["organisatie_eenheid_id"] is None
        and not perm_ctx.has_system_permission("lead:update")
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Alleen systeembeheerders maken een lead weer organisatiebreed",
        )
    await require(db, perm_ctx, take_away, resource_type, record.id)
    await require(db, perm_ctx, f"{resource_type}:create", resource_type, place=new)


async def _require_opdracht_move(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    old: dict[str, Any],
    new: dict[str, Any],
) -> None:
    for field, before in old.items():
        if new[field] == before:
            continue
        for eenheid_id in (before, new[field]):
            if eenheid_id is not None:
                await require(
                    db, perm_ctx, "opdracht:update", "opdracht", eenheid_id=eenheid_id
                )
    if all(v is None for v in new.values()) and not perm_ctx.has_system_permission(
        "opdracht:update"
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Alleen systeembeheerders halen alle eenheden van een opdracht weg",
        )


async def _readable(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    resource_id: UUID | None,
) -> bool:
    """May the caller see that this existing resource exists?

    Only for types read by visibility (step 0); the others (an eenheid, a
    tag, a samenwerkingsverband) are known tenant-wide.  A new resource
    (no id) has nothing to hide.
    """
    if resource_id is None or resource_type not in _READ_BY_VISIBILITY:
        return True
    read = f"{_domain(resource_type)}:read"
    return bool(await _decide(db, perm_ctx, read, resource_type, resource_id, None))


def requires(permission: str, resource_type: str, *, path_param: str = "id"):
    """Dependency factory: ``require`` with the resource id from the path.

    The dependency declares *path_param* as a ``UUID`` path parameter, so
    FastAPI answers 422 for a malformed id before anything is decided.

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
        db: AsyncSession,
        perm_ctx: PermissionContext,
        **path: UUID,
    ) -> PermissionContext:
        await require(db, perm_ctx, permission, resource_type, path[path_param])
        return perm_ctx

    _authz_requires.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                "db",
                inspect.Parameter.KEYWORD_ONLY,
                default=Depends(get_db),
                annotation=AsyncSession,
            ),
            inspect.Parameter(
                "perm_ctx",
                inspect.Parameter.KEYWORD_ONLY,
                default=Depends(get_permission_context),
                annotation=PermissionContext,
            ),
            inspect.Parameter(
                path_param,
                inspect.Parameter.KEYWORD_ONLY,
                default=Path(),
                annotation=UUID,
            ),
        ],
        return_annotation=PermissionContext,
    )
    return _authz_requires


__all__ = [
    "RESOURCE_TYPES",
    "EenheidRights",
    "can",
    "can_anywhere",
    "eenheid_ids_where",
    "get_eenheid_ids",
    "memberships",
    "org_visibility",
    "own_eenheid_where",
    "perm_ctx_for",
    "prefetch",
    "readable_modules",
    "require",
    "require_move",
    "requires",
    "rights_on_eenheid",
    "role_read_ids",
    "self_and_ancestor_ids",
    "visibility",
    "write_eenheid_ids",
]
