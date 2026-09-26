"""Central authorization decisions for grant-bearing actions.

Every check that decides whether someone may change *who has access to
what* lives here: placing people in an eenheid, assigning roles, naming a
manager, editing someone's identity (emails), and granting resource roles.
Routes and services call these helpers instead of composing their own
checks from ``require_permission`` and ``check_org_scope``.

Inheritance rule: a role held on an eenheid also applies to every
descendant of that eenheid.  So "effective on E" means: held as a system
role, or held on E or on any ancestor of E.  Visibility (seeing an
eenheid) never implies any of these rights.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.permissions import (
    RESOURCE_ROLE_PERMISSIONS,
    PermissionContext,
)
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.role import PersonRole, Role

# Roles that make someone responsible for the members of an eenheid (and
# of everything below it).
MEMBER_MANAGER_ROLES = frozenset({"unit_manager", "ministry_admin"})

# Eenheid types that form the internal organisation.  Everything else
# (gemeente, zbo, marktpartij, ...) is an external organisation that people
# are linked to as contacts.
INTERNAL_EENHEID_TYPES = frozenset(
    {
        "ministerie",
        "directoraat_generaal",
        "directie",
        "afdeling",
        "cluster",
        "bureau",
        "team",
    }
)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def eenheid_chain(db: AsyncSession, eenheid_id: UUID) -> list[UUID]:
    """Return ``[eenheid_id, parent, grandparent, ...]`` up to the root."""
    chain: list[UUID] = []
    current: UUID | None = eenheid_id
    while current is not None and current not in chain:
        chain.append(current)
        current = await db.scalar(
            select(OrganisatieEenheid.parent_id).where(OrganisatieEenheid.id == current)
        )
    return chain


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
) -> EenheidRights:
    """Resolve what *perm_ctx* may do on *eenheid_id*, inheriting downward."""
    if perm_ctx.is_super_admin:
        return EenheidRights(frozenset(), frozenset(), is_super_admin=True)

    roles: set[str] = set(perm_ctx.system_roles)
    permissions: set[str] = set(perm_ctx.system_permissions)
    for eid in await eenheid_chain(db, eenheid_id):
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
# Membership
# ---------------------------------------------------------------------------


async def can_manage_members(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid_id: UUID,
) -> bool:
    """True if the person manages *eenheid_id* or one of its ancestors."""
    rights = await rights_on_eenheid(db, perm_ctx, eenheid_id)
    return rights.has_role(*MEMBER_MANAGER_ROLES)


async def managed_subtree_ids(
    db: AsyncSession, perm_ctx: PermissionContext
) -> set[UUID] | None:
    """Eenheden whose members the person manages; ``None`` means all."""
    if perm_ctx.is_super_admin:
        return None
    from bouwmeester.core.org_context import _walk_children

    roots = [
        eid
        for eid, roles in perm_ctx.scoped_roles.items()
        if MEMBER_MANAGER_ROLES & set(roles)
    ]
    return set(roots) | await _walk_children(db, roots)


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
) -> None:
    """Guard creating, changing or ending a placement of *person* in *eenheid*.

    A placement of an account grants access (implicit viewer, visibility of
    the eenheid and its ancestors), so only a manager of the eenheid or of
    an ancestor may change it; everyone else files a placement request.

    Placing a contact is ordinary contact administration (a counterpart at
    another ministry or a gemeente) and stays open to ``people:update``.  A
    contact only becomes an account when its exact email is whitelisted by
    an admin and that person logs in with it.
    """
    if await can_manage_members(db, perm_ctx, eenheid.id):
        return
    if perm_ctx.has_permission("people:update") and not await is_account(db, person):
        return
    raise _forbidden(
        "Alleen een leidinggevende van deze eenheid kan hier iemand plaatsen. "
        "Dien een plaatsingsverzoek in."
    )


async def require_can_attach(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    eenheid_type: str,
    parent_id: UUID | None,
) -> None:
    """Guard moving an existing eenheid of *eenheid_type* under *parent_id*.

    Whoever manages the parent manages everything below it, and members see
    all their ancestors, so moving an eenheid into (or within) the internal
    organisation requires managing the new parent.  External organisations
    can be arranged freely by anyone allowed to edit them.
    """
    if perm_ctx.is_super_admin:
        return
    parent_type = (
        await db.scalar(
            select(OrganisatieEenheid.type).where(OrganisatieEenheid.id == parent_id)
        )
        if parent_id is not None
        else None
    )
    internal = (
        eenheid_type in INTERNAL_EENHEID_TYPES or parent_type in INTERNAL_EENHEID_TYPES
    )
    if not internal:
        return
    if parent_id is not None and await can_manage_members(db, perm_ctx, parent_id):
        return
    raise _forbidden(
        "Alleen een leidinggevende van de bovenliggende eenheid kan hier een "
        "eenheid onder hangen"
    )


async def require_can_decide_placement_request(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    requester_id: UUID,
    eenheid_id: UUID,
) -> None:
    """Guard approving or denying a placement request."""
    if perm_ctx.is_super_admin:
        return
    if requester_id == perm_ctx.person_id:
        raise _forbidden("Je kunt niet over je eigen verzoek beslissen")
    if not await can_manage_members(db, perm_ctx, eenheid_id):
        raise _forbidden("Geen bevoegdheid")


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


async def _role_rank(db: AsyncSession, role_ids: set[str]) -> int:
    if not role_ids:
        return 0
    ranks = await db.scalars(select(Role.rank).where(Role.id.in_(role_ids)))
    return max(ranks, default=0)


async def require_role_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    role: Role,
    eenheid_id: UUID | None,
) -> None:
    """Guard granting or revoking *role* on *eenheid_id*, whoever it is for.

    System roles are super_admin-only.  Otherwise ``people:assign_role``
    must be effective on the eenheid and *role* must rank below the
    caller's highest role there.
    """
    if perm_ctx.is_super_admin:
        return
    if eenheid_id is None:
        raise _forbidden("Alleen systeembeheerders kennen systeemrollen toe")
    rights = await rights_on_eenheid(db, perm_ctx, eenheid_id)
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
    await require_role_authority(db, perm_ctx, role=role, eenheid_id=eenheid_id)


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
    await require_role_authority(
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
        await require_role_authority(db, perm_ctx, role=role, eenheid_id=eenheid_id)
    else:
        await require_can_assign_role(
            db,
            perm_ctx,
            role=role,
            eenheid_id=eenheid_id,
            target_person_id=new_manager_id,
        )


# ---------------------------------------------------------------------------
# Person records
# ---------------------------------------------------------------------------


async def require_can_edit_person(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
) -> None:
    """Guard editing a person's record, emails and phone numbers.

    Emails decide which login maps to which person, so an account may only
    be edited by that person or by a people-manager.  Contacts may be
    maintained by anyone with ``people:update``.
    """
    if perm_ctx.is_super_admin or person.id == perm_ctx.person_id:
        return
    if perm_ctx.has_permission("people:manage"):
        return
    if not await is_account(db, person) and perm_ctx.has_permission("people:update"):
        return
    raise _forbidden("Alleen de persoon zelf of een beheerder kan dit wijzigen")


async def require_can_delete_person(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
) -> None:
    """Guard deleting a person.

    Deleting cascades to their roles, placements and resource grants, so an
    account (anyone who can log in or holds a role) is super_admin-only.
    Contacts can be cleaned up by a people-manager.
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


def require_valid_resource_role(resource_type: str, rol: str) -> None:
    """422 unless *rol* is a known role for *resource_type*."""
    if rol not in RESOURCE_ROLE_PERMISSIONS.get(resource_type, {}):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Onbekende rol '{rol}' voor {resource_type}",
        )
