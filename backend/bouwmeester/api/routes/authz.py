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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core import authority
from bouwmeester.core.authz import RESOURCE_TYPES, can, can_anywhere, prefetch
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.role import PersonRole, Role
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
from bouwmeester.repositories.resource_permission import ResourcePermissionRepository
from bouwmeester.schema.authz import (
    AuthzDecision,
    AuthzEvaluation,
    AuthzEvaluationsRequest,
    AuthzEvaluationsResponse,
    AuthzResourceProperties,
)

router = APIRouter(prefix="/authz", tags=["authz"])

_NO_PROPERTIES = AuthzResourceProperties()


async def _grant_resource_role(
    db: AsyncSession, perm_ctx: PermissionContext, ev: AuthzEvaluation
) -> None:
    props = ev.resource.properties or _NO_PROPERTIES
    if ev.resource.id is None or props.rol is None:
        raise HTTPException(422)
    await authority.require_can_grant_resource_role(
        db,
        perm_ctx,
        resource_type=ev.resource.type,
        resource_id=ev.resource.id,
        rol=props.rol,
        target_person_id=props.target_person_id,
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
        raise HTTPException(422)
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
    eenheid = await _eenheid(db, ev)
    manager = await OrganisatieEenheidRepository(db).get_current_manager_id(eenheid.id)
    await authority.require_can_dissolve_eenheid(
        db, perm_ctx, eenheid, has_manager=manager is not None
    )


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
    """Removing a person's rol on a resource, as the grant routes decide it."""
    props = ev.resource.properties or _NO_PROPERTIES
    if ev.resource.id is None or props.target_person_id is None:
        raise HTTPException(422)
    grants = await ResourcePermissionRepository(db).find_grants(
        ev.resource.type, ev.resource.id, person_id=props.target_person_id
    )
    grants = [g for g in grants if props.rol is None or g.rol == props.rol]
    if not grants:
        raise HTTPException(404)
    for grant in grants:
        await authority.require_can_change_resource_role(
            db, perm_ctx, grant, new_rol=None
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
      in that eenheid (no eenheid: where no eenheid applies).  For a
      sub-eenheid: ``org:create`` on ``organisatie_eenheid`` with the parent
      as ``eenheid_id``.  A child on an existing parent is asked on the
      parent: ``task:create`` on a ``corpus_node``, ``lead:create`` on an
      ``initiatief``.
    - ``properties.anywhere: true`` (no id): is there any eenheid where the
      caller may create this?  For generic create buttons (a task, a lead
      without initiatief).

    Grant actions (``core.authority`` guards, the same the routes call):

    - ``resource_role:grant``, resource ``{type, id}``, ``properties.rol``,
      optional ``properties.target_person_id``: hand out a rol on a resource
      (add a member, contact, betrokkene).  Without a target: to someone
      other than the caller.
    - ``resource_role:revoke``, resource ``{type, id}``,
      ``properties.target_person_id``, optional ``properties.rol`` (none:
      every rol of that person): remove it.  Leaving yourself is allowed,
      removing the last eigenaar is not.
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
    - ``eenheid:dissolve``, resource ``{type: "organisatie_eenheid", id}``.
    - ``person:place``, resource ``{type: "person", id?}``,
      ``properties.eenheid_id``, optional ``properties.ending`` (end the
      placement) and ``properties.contact`` (no id: a contact without
      account).  Without an id: place another person's account there.
    """
    await _prefetch(db, perm_ctx, data.evaluations)
    decisions = [
        AuthzDecision(decision=await _evaluate(db, perm_ctx, evaluation))
        for evaluation in data.evaluations
    ]
    return AuthzEvaluationsResponse(evaluations=decisions)
