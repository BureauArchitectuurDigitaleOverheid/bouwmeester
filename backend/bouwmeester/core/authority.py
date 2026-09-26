"""Authority over grants: who may change who has access to what.

Every decision about handing out or changing access lives here: placing
people in an eenheid, naming a manager, moving an eenheid, assigning roles,
editing someone's identity, and granting roles on a resource.  Routes and
services call these guards instead of composing their own checks.

Two layers sit below this module: ``core.permissions`` resolves what a
person holds (roles and permissions per eenheid) and ``core.org_context``
decides what a person can see.  Seeing an eenheid never implies authority
over it.

Inheritance rule: a role held on an eenheid also applies to every eenheid
below it.  "Effective on E" therefore means: held as a system role, or held
on E or on any ancestor of E.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.permissions import (
    RESOURCE_ROLE_PERMISSIONS,
    PermissionContext,
    check_resource_permission,
)
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import (
    INTERNAL_EENHEID_TYPES,
    OrganisatieEenheid,
)
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole, Role
from bouwmeester.repositories.org_tree import (
    get_membership_ids,
    get_self_and_ancestor_ids,
    get_subtree_ids,
)
from bouwmeester.repositories.resource_scope import get_authority_eenheid_ids

# Roles that make someone responsible for the members of an eenheid (and
# of everything below it).
MEMBER_MANAGER_ROLES = frozenset({"unit_manager", "ministry_admin"})


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# ---------------------------------------------------------------------------
# Rights on an eenheid
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
    for eid in await get_self_and_ancestor_ids(db, eenheid_id):
        roles.update(perm_ctx.scoped_roles.get(eid, ()))
        permissions |= perm_ctx.scoped_permissions.get(eid, set())
    return EenheidRights(frozenset(roles), frozenset(permissions), False)


async def require_permission_on_eenheid(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    perm: str,
    eenheid_id: UUID,
) -> None:
    """403 unless *perm* is effective on *eenheid_id* (not just anywhere)."""
    rights = await rights_on_eenheid(db, perm_ctx, eenheid_id)
    if not rights.has(perm):
        raise _forbidden("Onvoldoende rechten voor deze organisatie-eenheid")


# ---------------------------------------------------------------------------
# Managing members
# ---------------------------------------------------------------------------


async def can_manage_members(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid_id: UUID,
) -> bool:
    """True if the person manages *eenheid_id* or one of its ancestors."""
    rights = await rights_on_eenheid(db, perm_ctx, eenheid_id)
    return rights.has_role(*MEMBER_MANAGER_ROLES)


def managed_eenheid_ids(perm_ctx: PermissionContext) -> list[UUID]:
    """Eenheden on which the person holds a manager role directly."""
    return [
        eid
        for eid, roles in perm_ctx.scoped_roles.items()
        if MEMBER_MANAGER_ROLES & set(roles)
    ]


async def managed_subtree_ids(
    db: AsyncSession, perm_ctx: PermissionContext
) -> set[UUID] | None:
    """Eenheden whose members the person manages; ``None`` means all."""
    if perm_ctx.is_super_admin:
        return None
    return await get_subtree_ids(db, managed_eenheid_ids(perm_ctx))


async def is_account(db: AsyncSession, person: Person) -> bool:
    """True if *person* can act in Bouwmeester (as opposed to a contact).

    Accounts are people who have logged in, agents, and anyone holding a
    role.  Contacts are records that others maintain about external people.
    """
    if person.oidc_subject is not None or person.is_agent:
        return True
    has_role = await db.scalar(
        select(PersonRole.id).where(PersonRole.person_id == person.id).limit(1)
    )
    return has_role is not None


async def require_can_place(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
    eenheid: OrganisatieEenheid,
    *,
    ending: bool = False,
) -> None:
    """Guard creating, changing or ending a placement of *person* in *eenheid*.

    A placement of an account grants access (implicit viewer, visibility of
    the eenheid and its ancestors), so only a manager of the eenheid or of
    an ancestor may create or change it; everyone else files a placement
    request.  Ending your own placement only gives access up, so that is
    always allowed.

    Placing a contact is ordinary contact administration (a counterpart at
    another ministry or a gemeente) and stays open to ``people:update``.
    """
    if ending and person.id == perm_ctx.person_id:
        return
    if await can_manage_members(db, perm_ctx, eenheid.id):
        return
    if perm_ctx.has_permission("people:update") and not await is_account(db, person):
        return
    raise _forbidden(
        "Alleen een leidinggevende van deze eenheid kan hier iemand plaatsen. "
        "Dien een plaatsingsverzoek in."
    )


async def hold_placements_for_approval(db: AsyncSession, person: Person) -> int:
    """Turn a contact's placements in the internal organisation into requests.

    Called when a contact becomes an account (its first login).  Contacts
    may be placed by anyone, so those placements were never approved; now
    that they would grant access, each becomes a pending placement request
    for a manager of the eenheid.  Links to external organisations stay.
    Returns the number of requests created.
    """
    result = await db.execute(
        select(PersonOrganisatieEenheid)
        .join(
            OrganisatieEenheid,
            OrganisatieEenheid.id == PersonOrganisatieEenheid.organisatie_eenheid_id,
        )
        .where(
            PersonOrganisatieEenheid.person_id == person.id,
            PersonOrganisatieEenheid.eind_datum.is_(None),
            OrganisatieEenheid.type.in_(INTERNAL_EENHEID_TYPES),
        )
    )
    placements = list(result.scalars().all())
    for placement in placements:
        db.add(
            OrgPlacementRequest(
                person_id=person.id,
                organisatie_eenheid_id=placement.organisatie_eenheid_id,
                dienstverband=placement.dienstverband,
            )
        )
        await db.delete(placement)
    return len(placements)


async def require_can_decide_placement_request(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    requester_id: UUID,
    eenheid_id: UUID,
) -> None:
    """Guard approving, denying or redirecting a placement request."""
    if perm_ctx.is_super_admin:
        return
    if requester_id == perm_ctx.person_id:
        raise _forbidden("Je kunt niet over je eigen verzoek beslissen")
    if not await can_manage_members(db, perm_ctx, eenheid_id):
        raise _forbidden("Geen bevoegdheid")


# ---------------------------------------------------------------------------
# Structure of the tree
# ---------------------------------------------------------------------------


async def _eenheid_type(db: AsyncSession, eenheid_id: UUID | None) -> str | None:
    if eenheid_id is None:
        return None
    return await db.scalar(
        select(OrganisatieEenheid.type).where(OrganisatieEenheid.id == eenheid_id)
    )


async def _has_internal_descendant(db: AsyncSession, eenheid_id: UUID) -> bool:
    below = await get_subtree_ids(db, [eenheid_id]) - {eenheid_id}
    if not below:
        return False
    hit = await db.scalar(
        select(OrganisatieEenheid.id)
        .where(
            OrganisatieEenheid.id.in_(below),
            OrganisatieEenheid.type.in_(INTERNAL_EENHEID_TYPES),
        )
        .limit(1)
    )
    return hit is not None


async def require_can_move_eenheid(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid: OrganisatieEenheid,
    *,
    new_parent_id: UUID | None,
    new_type: str,
) -> None:
    """Guard moving an eenheid or changing it between internal and external.

    Whoever manages a parent manages everything below it, and members see
    all their ancestors.  So when the internal organisation is involved
    (before or after, the eenheid, its parent or anything below it), the
    caller must manage the eenheid itself and the new parent.  Detaching
    into a new root is super_admin-only.  External organisations without
    internal parts can be arranged freely by anyone allowed to edit them.
    """
    if perm_ctx.is_super_admin:
        return
    if new_parent_id == eenheid.parent_id and new_type == eenheid.type:
        return
    involved = {
        eenheid.type,
        new_type,
        await _eenheid_type(db, eenheid.parent_id),
        await _eenheid_type(db, new_parent_id),
    }
    if not involved & INTERNAL_EENHEID_TYPES and not await _has_internal_descendant(
        db, eenheid.id
    ):
        return
    if not await can_manage_members(db, perm_ctx, eenheid.id):
        raise _forbidden(
            "Alleen een leidinggevende van deze eenheid kan hem verplaatsen "
            "of van soort veranderen"
        )
    if new_parent_id == eenheid.parent_id:
        return
    if new_parent_id is None:
        raise _forbidden("Alleen systeembeheerders maken een losse eenheid")
    if not await can_manage_members(db, perm_ctx, new_parent_id):
        raise _forbidden(
            "Alleen een leidinggevende van de nieuwe bovenliggende eenheid kan "
            "hier een eenheid onder hangen"
        )


async def require_can_dissolve_eenheid(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid: OrganisatieEenheid,
    *,
    has_manager: bool,
) -> None:
    """Guard dissolving an eenheid (``geldig_tot``).

    Dissolving ends the manager's role, so that needs the same authority as
    removing the manager.  An internal eenheid is only dissolved by someone
    who manages it.
    """
    if perm_ctx.is_super_admin:
        return
    if eenheid.type in INTERNAL_EENHEID_TYPES and not await can_manage_members(
        db, perm_ctx, eenheid.id
    ):
        raise _forbidden("Alleen een leidinggevende kan deze eenheid opheffen")
    if has_manager:
        await require_can_set_manager(
            db, perm_ctx, eenheid_id=eenheid.id, new_manager_id=None
        )


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


async def _role_rank(db: AsyncSession, role_ids: set[str]) -> int:
    if not role_ids:
        return 0
    ranks = await db.scalars(select(Role.rank).where(Role.id.in_(role_ids)))
    return max(ranks, default=0)


async def _require_role_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    role: Role,
    eenheid_id: UUID | None,
) -> None:
    """Guard granting or revoking *role* on *eenheid_id*, whoever it is for.

    System roles are super_admin-only.  Otherwise ``people:assign_role``
    must be effective on the eenheid through an organisational role
    (platform_admin operates the platform, it does not staff the
    organisation), and *role* must rank below the caller's highest role
    there.
    """
    if perm_ctx.is_super_admin:
        return
    if eenheid_id is None:
        raise _forbidden("Alleen systeembeheerders kennen systeemrollen toe")
    rights = await rights_on_eenheid(
        db, perm_ctx, eenheid_id, include_system_roles=False
    )
    if not rights.has("people:assign_role"):
        raise _forbidden("Geen bevoegdheid om rollen toe te kennen in deze eenheid")
    if role.rank >= await _role_rank(db, set(rights.roles)):
        raise _forbidden("Je kunt geen rol toekennen op of boven je eigen niveau")


async def require_can_assign_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    role: Role,
    eenheid_id: UUID | None,
    target_person_id: UUID,
) -> None:
    """Guard granting *role* to a person: authority, and never to yourself."""
    if not perm_ctx.is_super_admin and target_person_id == perm_ctx.person_id:
        raise _forbidden("Je kunt jezelf geen rol toekennen")
    await _require_role_authority(db, perm_ctx, role=role, eenheid_id=eenheid_id)


async def require_can_revoke_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    assignment: PersonRole,
) -> None:
    """Guard ending a role assignment.

    Giving up one of your own roles is always allowed, except your own
    super_admin role (that would lock the platform out of its last admin).
    """
    if assignment.person_id == perm_ctx.person_id:
        if assignment.role_id == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Je kunt je eigen systeembeheerder-rol niet intrekken",
            )
        return
    role = await db.get(Role, assignment.role_id)
    if role is None:
        raise _forbidden("Onbekende rol")
    await _require_role_authority(
        db, perm_ctx, role=role, eenheid_id=assignment.organisatie_eenheid_id
    )


async def require_can_set_manager(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    eenheid_id: UUID,
    new_manager_id: UUID | None,
) -> None:
    """Guard naming or clearing the manager of an eenheid.

    Setting ``manager_id`` ends the current ``unit_manager`` role and writes
    a new one, so it follows the same rules as assigning that role directly.
    """
    role = await db.get(Role, "unit_manager")
    if role is None:  # pragma: no cover - seeded by migrations
        raise _forbidden("Rol unit_manager ontbreekt")
    if new_manager_id is None:
        await _require_role_authority(db, perm_ctx, role=role, eenheid_id=eenheid_id)
    else:
        await require_can_assign_role(
            db,
            perm_ctx,
            role=role,
            eenheid_id=eenheid_id,
            target_person_id=new_manager_id,
        )


async def require_can_create_eenheid(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    parent_id: UUID | None,
    manager_id: UUID | None,
) -> None:
    """Guard creating an eenheid.

    Creating is free (stakeholder eenheden live anywhere): a new eenheid
    has no members, so it grants nobody anything.  Naming a manager does,
    and the new eenheid inherits its parent's rights, so the parent decides.
    """
    if manager_id is None or perm_ctx.is_super_admin:
        return
    if parent_id is None:
        raise _forbidden("Alleen systeembeheerders benoemen hier een leidinggevende")
    await require_can_set_manager(
        db, perm_ctx, eenheid_id=parent_id, new_manager_id=manager_id
    )


# ---------------------------------------------------------------------------
# Person records
# ---------------------------------------------------------------------------


async def _manages_person(
    db: AsyncSession, perm_ctx: PermissionContext, person: Person
) -> bool:
    """True if the caller manages one of the eenheden *person* is placed in."""
    for eenheid_id in await get_membership_ids(db, person.id):
        if await can_manage_members(db, perm_ctx, eenheid_id):
            return True
    return False


async def require_can_edit_person(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
    *,
    identity: bool,
) -> None:
    """Guard editing a person.

    ``identity`` covers email addresses: they decide which login maps to
    which person and who the admin seed promotes, so on an account only the
    person themselves or a super_admin may change them.  Other fields
    (naam, functie, phone numbers) may also be kept up to date by a manager
    of one of the person's eenheden.  Contacts are maintained by anyone
    with ``people:update``.
    """
    if perm_ctx.is_super_admin or person.id == perm_ctx.person_id:
        return
    if not await is_account(db, person):
        if perm_ctx.has_permission("people:update"):
            return
        raise _forbidden("Onvoldoende rechten")
    if identity:
        raise _forbidden(
            "Alleen de persoon zelf of een systeembeheerder kan e-mailadressen wijzigen"
        )
    if await _manages_person(db, perm_ctx, person):
        return
    raise _forbidden("Alleen de persoon zelf of een leidinggevende kan dit wijzigen")


async def require_can_delete_person(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
) -> None:
    """Guard deleting a person.

    Deleting cascades to their roles, placements and resource grants, so an
    account is super_admin-only.  Contacts can be cleaned up by a
    people-manager.
    """
    if perm_ctx.is_super_admin:
        return
    if await is_account(db, person):
        raise _forbidden("Alleen systeembeheerders kunnen accounts verwijderen")
    if not perm_ctx.has_permission("people:manage"):
        raise _forbidden("Onvoldoende rechten")


# ---------------------------------------------------------------------------
# Resource roles
# ---------------------------------------------------------------------------


def _require_known_rol(resource_type: str, rol: str) -> None:
    if rol not in RESOURCE_ROLE_PERMISSIONS.get(resource_type, {}):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Onbekende rol '{rol}' voor {resource_type}",
        )


async def _grant_reaches_caller(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    target_person_id: UUID | None,
    target_eenheid_id: UUID | None,
) -> bool:
    """True if a grant to this person or eenheid would benefit the caller.

    An eenheid grant counts for every member of that eenheid
    (``ResourcePermissionRepository.get_roles_for_person_resource``).
    """
    if perm_ctx.person_id is None:
        return False
    if target_person_id is not None:
        return target_person_id == perm_ctx.person_id
    if target_eenheid_id is not None:
        return target_eenheid_id in await get_membership_ids(db, perm_ctx.person_id)
    return False


async def _require_grant_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    resource_type: str,
    resource_id: UUID,
    owner_rol: bool,
    target_person_id: UUID | None,
    target_eenheid_id: UUID | None,
) -> None:
    """Authority to hand out (or change) a rol on a resource.

    - an eigenaar of the resource may hand out any rol;
    - otherwise ``resource_permission:manage`` must be effective on one of
      the eenheden that own the resource, and not for yourself (a grant to
      an eenheid you are a member of reaches you too);
    - a resource without such an eenheid only has its eigenaars, except that
      corpus nodes (tenant-wide today) take non-owner stakeholders, yourself
      included, from anyone with ``resource_permission:manage``.
    """
    if perm_ctx.is_super_admin:
        return
    if perm_ctx.person_id is not None and await check_resource_permission(
        db, perm_ctx.person_id, resource_type, resource_id, "resource_permission:manage"
    ):
        return

    found, eenheid_ids = await get_authority_eenheid_ids(db, resource_type, resource_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item niet gevonden")
    if resource_type == "corpus_node" and not eenheid_ids and not owner_rol:
        if perm_ctx.has_permission("resource_permission:manage"):
            return
        raise _forbidden("Onvoldoende rechten")
    if await _grant_reaches_caller(
        db,
        perm_ctx,
        target_person_id=target_person_id,
        target_eenheid_id=target_eenheid_id,
    ):
        raise _forbidden("Je kunt jezelf geen rol op dit item geven")
    for eenheid_id in eenheid_ids:
        rights = await rights_on_eenheid(db, perm_ctx, eenheid_id)
        if rights.has("resource_permission:manage"):
            return
    raise _forbidden("Alleen de eigenaar kan hier rollen toekennen")


async def _require_keeps_an_owner(
    db: AsyncSession, grant: ResourcePermission, new_rol: str | None
) -> None:
    """409 when the change would leave the resource without any eigenaar."""
    if grant.rol != "eigenaar" or new_rol == "eigenaar":
        return
    owners = await db.scalar(
        select(func.count())
        .select_from(ResourcePermission)
        .where(
            ResourcePermission.resource_type == grant.resource_type,
            ResourcePermission.resource_id == grant.resource_id,
            ResourcePermission.rol == "eigenaar",
            ResourcePermission.id != grant.id,
        )
    )
    if not owners:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Er moet minstens één eigenaar overblijven",
        )


async def require_can_grant_resource_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    resource_type: str,
    resource_id: UUID,
    rol: str,
    target_person_id: UUID | None = None,
    target_eenheid_id: UUID | None = None,
) -> None:
    """Guard giving *rol* on a resource to a person or an eenheid."""
    _require_known_rol(resource_type, rol)
    await _require_grant_authority(
        db,
        perm_ctx,
        resource_type=resource_type,
        resource_id=resource_id,
        owner_rol=rol == "eigenaar",
        target_person_id=target_person_id,
        target_eenheid_id=target_eenheid_id,
    )


async def require_can_change_resource_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    grant: ResourcePermission,
    *,
    new_rol: str | None,
) -> None:
    """Guard changing (``new_rol``) or removing (``None``) an existing grant.

    A resource never loses its last eigenaar this way.  Otherwise leaving a
    resource yourself is always allowed; anything else needs the authority
    to hand out both the current and the new rol.
    """
    await _require_keeps_an_owner(db, grant, new_rol)
    if new_rol is None and grant.person_id == perm_ctx.person_id:
        return
    if new_rol is not None:
        _require_known_rol(grant.resource_type, new_rol)
    await _require_grant_authority(
        db,
        perm_ctx,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        owner_rol="eigenaar" in {grant.rol, new_rol},
        target_person_id=grant.person_id,
        target_eenheid_id=grant.organisatie_eenheid_id,
    )
