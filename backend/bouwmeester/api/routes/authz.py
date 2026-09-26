"""AuthZEN-shaped evaluation endpoint: may the caller do these actions?

The frontend asks here instead of re-deriving rights from roles, so buttons
match what the API will allow.  A missing resource is ``false`` just like a
forbidden one, so this endpoint reveals no more than the routes do.

Actions on a resource (``"node:update"``, ``"lead:create"``, ...) are
decided by ``core.authz.can``.  Grant actions are decided by calling the
``core.authority`` guard the matching route calls; a refusal of any kind
is ``false``.  See :func:`evaluate` for the list.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_can_end_eenheid
from bouwmeester.core import authority
from bouwmeester.core.authz import (
    RESOURCE_TYPES,
    can,
    can_anywhere,
    eenheid_ids_where,
    prefetch,
)
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.role import PersonRole, Role
from bouwmeester.repositories.org_tree import get_subtree_ids
from bouwmeester.repositories.resource_permission import ResourcePermissionRepository
from bouwmeester.schema.authz import (
    AuthzDecision,
    AuthzEenhedenResponse,
    AuthzEvaluation,
    AuthzEvaluationsRequest,
    AuthzEvaluationsResponse,
    AuthzResourceProperties,
    EenheidAction,
)

router = APIRouter(prefix="/authz", tags=["authz"])

_NO_PROPERTIES = AuthzResourceProperties()


async def _grant_resource_role(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    if ev.resource.id is None or props.rol is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
    await authority.require_can_grant_resource_role(
        db,
        perm_ctx,
        resource_type=ev.resource.type,
        resource_id=ev.resource.id,
        rol=props.rol,
        target_person_id=props.target_person_id,
        target_eenheid_id=props.target_eenheid_id,
    )


async def _assign_role(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    if props.anywhere and props.role_id is None:
        await _assign_any_role(db, perm_ctx, props)
        return
    role = await db.get(Role, props.role_id) if props.role_id else None
    if role is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
    await authority.require_can_assign_role(
        db,
        perm_ctx,
        role=role,
        eenheid_id=props.eenheid_id,
        target_person_id=props.target_person_id,
    )


async def _assign_any_role(
    db: AsyncSession, perm_ctx: PermissionContext, props: AuthzResourceProperties
) -> None:
    """Refuse unless some role may go to someone else (in ``eenheid_id``).

    Without an eenheid: anywhere.  A role on an eenheid applies below it, so
    the eenheden where the caller holds a role are where it holds first.
    """
    places = (
        [props.eenheid_id]
        if props.eenheid_id is not None
        else [None, *perm_ctx.scoped_roles]
    )
    for role in (await db.scalars(select(Role))).all():
        for eenheid_id in places:
            try:
                await authority.require_can_assign_role(
                    db,
                    perm_ctx,
                    role=role,
                    eenheid_id=eenheid_id,
                    target_person_id=props.target_person_id,
                )
            except HTTPException:
                continue
            return
    raise HTTPException(403)


async def _revoke_role(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    assignment = await db.get(PersonRole, ev.resource.id) if ev.resource.id else None
    if assignment is None:
        raise HTTPException(404)
    await authority.require_can_revoke_role(db, perm_ctx, assignment)


async def _eenheid(db: AsyncSession, ev: AuthzEvaluation) -> OrganisatieEenheid:
    eenheid = (
        await db.get(OrganisatieEenheid, ev.resource.id) if ev.resource.id else None
    )
    if eenheid is None:
        raise HTTPException(404)
    return eenheid


async def _set_manager(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    eenheid = await _eenheid(db, ev)
    await authority.require_can_set_manager(
        db, perm_ctx, eenheid_id=eenheid.id, new_manager_id=props.target_person_id
    )


async def _dissolve(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    await require_can_end_eenheid(db, perm_ctx, await _eenheid(db, ev))


async def _place(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    eenheid = (
        await db.get(OrganisatieEenheid, props.eenheid_id) if props.eenheid_id else None
    )
    if eenheid is None:
        raise HTTPException(404)
    person = None
    if ev.resource.id is not None:
        person = await db.get(Person, ev.resource.id)
        if person is None:
            raise HTTPException(404)
    # No one in particular (person None): another account, the strictest
    # case, or a contact with ``contact``.  The routes call the same guard.
    await authority.require_can_place(
        db, perm_ctx, person, eenheid, ending=props.ending, contact=props.contact
    )


async def _revoke_resource_role(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    """Removing a rol of a person or an eenheid, as the grant routes decide it."""
    props = ev.resource.properties or _NO_PROPERTIES
    if ev.resource.id is None or (
        (props.target_person_id is None) == (props.target_eenheid_id is None)
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
    grants = await ResourcePermissionRepository(db).find_grants(
        ev.resource.type,
        ev.resource.id,
        person_id=props.target_person_id,
        eenheid_id=props.target_eenheid_id,
    )
    grants = [g for g in grants if props.rol is None or g.rol == props.rol]
    if not grants:
        raise HTTPException(404)
    for grant in grants:
        await authority.require_can_change_resource_role(
            db, perm_ctx, grant, new_rol=None
        )


async def _name_owner(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    if (
        ev.resource.type != "corpus_node"
        or ev.resource.id is None
        or props.target_person_id is None
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
    await authority.require_can_name_owner(
        db, perm_ctx, ev.resource.id, props.target_person_id
    )


async def _share(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    if ev.resource.type != "organisatie_eenheid" or ev.resource.id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
    await authority.require_can_share(
        db,
        perm_ctx,
        source_eenheid_id=ev.resource.id,
        source_node_id=None,
        target_eenheid_id=props.target_eenheid_id,
    )


Guard = Callable[[AsyncSession, PermissionContext, AuthzEvaluation], Awaitable[None]]

GRANT_ACTIONS: dict[str, Guard] = {
    "resource_role:grant": _grant_resource_role,
    "resource_role:revoke": _revoke_resource_role,
    "role:assign": _assign_role,
    "role:revoke": _revoke_role,
    "eenheid:set_manager": _set_manager,
    "eenheid:dissolve": _dissolve,
    "person:place": _place,
    "parlementair:name_owner": _name_owner,
    "eenheid:share": _share,
}


async def _evaluate(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> bool:
    if not perm_ctx.is_authenticated:
        return False
    guard = GRANT_ACTIONS.get(ev.action)
    if guard is not None:
        try:
            await guard(db, perm_ctx, ev)
        except HTTPException:
            return False
        return True

    resource = ev.resource
    props = resource.properties or _NO_PROPERTIES
    try:
        if props.anywhere and resource.id is None:
            return await can_anywhere(db, perm_ctx, ev.action, resource.type)
        if props.eenheid_type is not None and resource.id is None:
            # A new eenheid of this type below ``eenheid_id`` (or at the top).
            place = {"parent_id": props.eenheid_id, "type": props.eenheid_type}
            return await can(db, perm_ctx, ev.action, resource.type, place=place)
        return await can(
            db,
            perm_ctx,
            ev.action,
            resource.type,
            resource.id,
            eenheid_id=props.eenheid_id,
        )
    except ValueError:
        # A question can() does not decide (an existing person): no.
        return False


async def _prefetch(
    db: AsyncSession, perm_ctx: PermissionContext, evaluations: list[AuthzEvaluation]
) -> None:
    """Locate every resource asked about in one query per type.

    A board asks about each of its leads, a node page about each of its
    edges: without this, every question would cost its own lookups.
    """
    if not perm_ctx.is_authenticated:
        return
    ids: dict[str, set] = {}
    for ev in evaluations:
        if ev.resource.id is not None and ev.action not in GRANT_ACTIONS:
            ids.setdefault(ev.resource.type, set()).add(ev.resource.id)
    for resource_type, resource_ids in ids.items():
        if resource_type in RESOURCE_TYPES - {"person"}:
            await prefetch(db, perm_ctx, resource_type, resource_ids)


@router.post("/evaluations", response_model=AuthzEvaluationsResponse)
async def evaluate(
    data: AuthzEvaluationsRequest,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> AuthzEvaluationsResponse:
    """Decide each evaluation for the caller, in order.

    Resource actions (``core.authz.can``):

    - ``{action: "<perm>", resource: {type, id}}``: an existing resource.
    - ``{action, resource: {type, properties: {eenheid_id}}}``: creating one
      in that eenheid (no eenheid: where no eenheid applies).  A child on
      an existing parent is asked on the parent: ``task:create`` on a
      ``corpus_node``, ``lead:create`` on an ``initiatief``.
    - A new eenheid: ``org:create`` on ``organisatie_eenheid`` with
      ``properties.eenheid_type`` and optional ``properties.eenheid_id``
      (the parent).  An internal type needs ``org:create`` on the parent
      (no parent: system roles only), and so does an external type below a
      parent that touches the internal organisation; elsewhere an external
      type is free for anyone holding ``org:create`` somewhere.  Without
      ``eenheid_type`` and with ``eenheid_id``: an internal eenheid below it.
    - ``properties.anywhere: true`` (no id): is there any eenheid where the
      caller may create this?  For generic create buttons (a task, a lead
      without initiatief).  For ``lead:create`` on ``lead`` this is exactly
      what ``POST /api/leads`` without initiatief and eenheid allows (the
      lead lands in the caller's own eenheid; with none, system roles
      only); in an initiatief ask ``lead:create`` on that ``initiatief``.

    Grant actions (``core.authority`` guards, the same the routes call):

    - ``resource_role:grant``, resource ``{type, id}``, ``properties.rol``,
      optional ``properties.target_person_id`` or
      ``properties.target_eenheid_id``: hand out a rol on a resource to a
      person or an eenheid (add a member, contact, betrokkene, partner
      eenheid).  Without a target: to a person other than the caller.
    - ``resource_role:revoke``, resource ``{type, id}``, exactly one of
      ``properties.target_person_id`` and ``properties.target_eenheid_id``,
      optional ``properties.rol`` (none: every rol of that holder): remove
      it.  Leaving yourself is allowed, removing the last eigenaar is not.
    - ``role:assign``, resource ``{type: "role"}``, ``properties.role_id``,
      optional ``properties.eenheid_id`` (none: a system role) and
      ``properties.target_person_id``.  With ``properties.anywhere: true``
      and no ``role_id``: is there any role the caller may assign to
      someone else (in ``eenheid_id`` when given, else anywhere).
    - ``role:revoke``, resource ``{type: "role", id}`` with the id of the
      role assignment.
    - ``eenheid:set_manager``, resource ``{type: "organisatie_eenheid", id}``,
      optional ``properties.target_person_id`` (none: clear or name someone
      else).
    - ``eenheid:dissolve``, resource ``{type: "organisatie_eenheid", id}``:
      ending it (``geldig_tot``) or deleting it, the same guard.
    - ``person:place``, resource ``{type: "person", id?}``,
      ``properties.eenheid_id``, optional ``properties.ending`` (end the
      placement) and ``properties.contact`` (no id: a contact without
      account).  Without an id: place another person's account there.
    - ``parlementair:name_owner``, resource ``{type: "corpus_node", id}``,
      ``properties.target_person_id``: make that person the eigenaar of the
      node when completing the review of its parliamentary item
      (``require_can_name_owner``, the guard the complete route calls).
    - ``eenheid:share``, resource ``{type: "organisatie_eenheid", id}`` (the
      source), ``properties.target_eenheid_id``: share the source with that
      eenheid (``require_can_share``, the guard ``POST /api/sharing``
      calls).  Without a target: with an eenheid the caller is not in.
    """
    await _prefetch(db, perm_ctx, data.evaluations)
    decisions = [
        AuthzDecision(decision=await _evaluate(db, perm_ctx, evaluation))
        for evaluation in data.evaluations
    ]
    return AuthzEvaluationsResponse(evaluations=decisions)


# ---------------------------------------------------------------------------
# Where may the caller do this? (``GET /api/authz/eenheden``)
# ---------------------------------------------------------------------------

# Each returns the eenheden where the action is allowed, or None for all.
EenhedenWhere = Callable[[AsyncSession, PermissionContext], Awaitable[set[UUID] | None]]


def _org_where(permission: str) -> EenhedenWhere:
    async def where(db: AsyncSession, perm_ctx: PermissionContext) -> set[UUID] | None:
        return await eenheid_ids_where(db, perm_ctx, permission)

    return where


async def _assign_role_where(
    db: AsyncSession, perm_ctx: PermissionContext
) -> set[UUID] | None:
    """Where ``people:assign_role`` holds for ``core.authority``'s role guard.

    Through an organisational role on the eenheid or above it (system roles
    other than super_admin do not count there).
    """
    if perm_ctx.is_super_admin:
        return None
    return await get_subtree_ids(
        db,
        [
            eid
            for eid, perms in perm_ctx.scoped_permissions.items()
            if "people:assign_role" in perms
        ],
    )


async def _place_where(
    db: AsyncSession, perm_ctx: PermissionContext
) -> set[UUID] | None:
    """Where the caller may place another person's account (``require_can_place``).

    ``people:update`` somewhere, and managing the eenheid or one above it.
    """
    if not perm_ctx.has_permission("people:update"):
        return set()
    return await authority.managed_subtree_ids(db, perm_ctx)


_EENHEDEN_WHERE: dict[str, EenhedenWhere] = {
    "org:manage": _org_where("org:manage"),
    "org:update": _org_where("org:update"),
    "people:assign_role": _assign_role_where,
    "person:place": _place_where,
}


@router.get("/eenheden", response_model=AuthzEenhedenResponse)
async def eenheden_allowed(
    action: EenheidAction = Query(...),
    eenheid_type: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> AuthzEenhedenResponse:
    """The eenheden where the caller may do *action*, for pickers and admin lists.

    The same decision as asking the evaluation endpoint per eenheid:

    - ``org:update``, ``org:manage``: on the eenheid itself (synced eenheden
      are read-only, so they are left out);
    - ``org:create``: creating an eenheid of ``eenheid_type`` below it (no
      type: an internal one).  Inside the internal organisation that needs
      ``org:create`` on the parent, for an external type too; an external
      type may go below any eenheid outside it.  Creating one at the top
      is asked through the evaluation endpoint;
    - ``people:assign_role``: some role may be assigned there;
    - ``person:place``: another person's account may be placed there.

    ``{"all": true}`` means everywhere (a system role); ``ids`` is then
    empty.  A role on an eenheid applies below it, so ``ids`` holds whole
    subtrees.
    """
    if not perm_ctx.is_authenticated:
        return AuthzEenhedenResponse(all=False, ids=[])
    if action == "org:create":
        ids = await eenheid_ids_where(
            db, perm_ctx, "org:create", eenheid_type=eenheid_type
        )
    else:
        ids = await _EENHEDEN_WHERE[action](db, perm_ctx)
    return AuthzEenhedenResponse(all=ids is None, ids=sorted(ids or (), key=str))
