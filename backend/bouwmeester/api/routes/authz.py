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
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core import authority
from bouwmeester.core.authz import can, can_anywhere
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.role import Role
from bouwmeester.repositories.organisatie_eenheid import OrganisatieEenheidRepository
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
    if ev.resource.id is not None:
        person = await db.get(Person, ev.resource.id)
        if person is None:
            raise HTTPException(404)
    else:
        # No one in particular: ask about another person's account, the
        # strictest case (placing an account grants access).
        person = Person(id=uuid4(), naam="", oidc_subject="evaluation")
    await authority.require_can_place(db, perm_ctx, person, eenheid)


Guard = Callable[[AsyncSession, PermissionContext, AuthzEvaluation], Awaitable[None]]

GRANT_ACTIONS: dict[str, Guard] = {
    "resource_role:grant": _grant_resource_role,
    "role:assign": _assign_role,
    "eenheid:set_manager": _set_manager,
    "eenheid:dissolve": _dissolve,
    "person:place": _place,
}


async def _decide(
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
      in that eenheid (no eenheid: where no eenheid applies).
    - ``properties.anywhere: true`` (no id): is there any eenheid where the
      caller may create this?  For generic create buttons (a task, a lead
      without initiatief).

    Grant actions (``core.authority`` guards, the same the routes call):

    - ``resource_role:grant``, resource ``{type, id}``, ``properties.rol``,
      optional ``properties.target_person_id``: hand out a rol on a resource
      (add a member, contact, betrokkene).  Without a target: to someone
      other than the caller.
    - ``role:assign``, resource ``{type: "role"}``, ``properties.role_id``,
      optional ``properties.eenheid_id`` (none: a system role) and
      ``properties.target_person_id``.
    - ``eenheid:set_manager``, resource ``{type: "organisatie_eenheid", id}``,
      optional ``properties.target_person_id`` (none: clear or name someone
      else).
    - ``eenheid:dissolve``, resource ``{type: "organisatie_eenheid", id}``.
    - ``person:place``, resource ``{type: "person", id?}``,
      ``properties.eenheid_id``.  Without an id: place another person's
      account there.
    """
    decisions = [
        AuthzDecision(decision=await _decide(db, perm_ctx, evaluation))
        for evaluation in data.evaluations
    ]
    return AuthzEvaluationsResponse(evaluations=decisions)
