"""Authority over grants: who may change who has access to what.

Every decision about handing out or changing access lives here: placing
people in an eenheid, naming a manager, moving an eenheid, assigning roles,
editing someone's identity, granting roles on a resource, and sharing an
eenheid or node with another eenheid.  Routes and services call these
guards instead of composing their own checks.

Three layers sit below this module: ``core.permissions`` resolves what a
person holds (roles and permissions per eenheid), ``core.authz`` decides
whether a person may do an action on a resource, and ``core.org_context``
decides what a person can see.  Seeing an eenheid never implies authority
over it.

Inheritance rule: a role held on an eenheid also applies to every eenheid
below it.  "Effective on E" therefore means: held as a system role, or held
on E or on any ancestor of E.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can, get_eenheid_ids, require, rights_on_eenheid
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.core.resource_roles import RESOURCE_ROLE_PERMISSIONS
from bouwmeester.models.corpus_node import CorpusNode
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
    touches_organisation,
)

# Roles that make someone responsible for the members of an eenheid (and
# of everything below it).
MEMBER_MANAGER_ROLES = frozenset({"unit_manager", "ministry_admin"})


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


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


async def member_manager_ids(db: AsyncSession, eenheid_id: UUID) -> set[UUID]:
    """People who may decide about the members of *eenheid_id*.

    Everyone holding a manager role on the eenheid or on any eenheid above
    it: the same set ``can_manage_members`` lets through.
    """
    chain = await get_self_and_ancestor_ids(db, eenheid_id)
    today = date.today()
    result = await db.execute(
        select(PersonRole.person_id).where(
            PersonRole.organisatie_eenheid_id.in_(chain),
            PersonRole.role_id.in_(MEMBER_MANAGER_ROLES),
            PersonRole.start_datum <= today,
            (PersonRole.eind_datum.is_(None)) | (PersonRole.eind_datum >= today),
        )
    )
    return set(result.scalars().all())


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
    person: Person | None,
    eenheid: OrganisatieEenheid,
    *,
    ending: bool = False,
    contact: bool = False,
) -> None:
    """Guard creating, changing or ending a placement of *person* in *eenheid*.

    Every placement change needs ``people:update``.  A placement of an
    account grants access (implicit viewer, visibility of the eenheid and
    its ancestors), so only a manager of the eenheid or of an ancestor may
    create or change it; everyone else files a placement request.  Nobody
    places themselves, managers included (a manager would otherwise join any
    eenheid below them); ending your own placement only gives access up, so
    that is always allowed.

    Placing a contact is ordinary contact administration (a counterpart at
    another ministry or a gemeente) and stays open to ``people:update``.
    Such a placement grants nothing until the contact logs in, and then
    ``hold_unconfirmed_placements`` turns it into a placement request.

    Without a concrete person (the evaluation endpoint), ``person=None``
    asks about someone else: another account (strictest), or a contact
    with ``contact=True``.  ``contact`` is ignored when *person* is given.
    """
    if not perm_ctx.is_authenticated:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Niet ingelogd")
    if not perm_ctx.has_permission("people:update"):
        raise _forbidden("Onvoldoende rechten")
    own = person is not None and person.id == perm_ctx.person_id
    if own and ending:
        return
    if own and not perm_ctx.is_super_admin:
        raise _forbidden(
            f"Je kunt jezelf niet in {eenheid.naam} plaatsen. Dien een "
            "plaatsingsverzoek in; een leidinggevende beslist."
        )
    if await can_manage_members(db, perm_ctx, eenheid.id):
        return
    if contact if person is None else not await is_account(db, person):
        return
    # Linking your own staff to an external organisation (a detachering) is
    # the person's manager's call: it grants nothing inside the organisation.
    # One that hangs inside it does (members see up the line), so there
    # its managers decide like anywhere else in the organisation.
    if (
        person is not None
        and eenheid.type not in INTERNAL_EENHEID_TYPES
        and not await touches_organisation(db, eenheid.id)
        and await _manages_person(db, perm_ctx, person)
    ):
        return
    ask = await _who_decides(db, eenheid)
    if ending:
        raise _forbidden(
            "Alleen de persoon zelf of een leidinggevende kan deze plaatsing "
            f"beëindigen. {ask}"
        )
    raise _forbidden(
        f"Alleen een leidinggevende kan iemand in {eenheid.naam} plaatsen. {ask}"
    )


# ``PersonOrganisatieEenheid.bron`` of a placement a manager made or approved.
# Manual placements with any other bron ("handmatig") were contact
# administration and are not trusted when the contact logs in.
CONFIRMED_PLACEMENT_BRON = "leidinggevende"
_UNCONFIRMED_PLACEMENT_BRON = "handmatig"


async def placement_bron(
    db: AsyncSession, perm_ctx: PermissionContext, eenheid_id: UUID
) -> str:
    """The bron to record for a placement the caller makes in *eenheid_id*."""
    if await can_manage_members(db, perm_ctx, eenheid_id):
        return CONFIRMED_PLACEMENT_BRON
    return _UNCONFIRMED_PLACEMENT_BRON


async def hold_unconfirmed_placements(db: AsyncSession, person: Person) -> None:
    """Turn unconfirmed placements into requests when a contact becomes an account.

    Anyone with ``people:update`` may place a contact anywhere (contact
    administration).  When that contact's first login links to the record,
    those placements would suddenly grant access (implicit viewer,
    visibility up the line).  So every active manual placement in or below
    the internal organisation that no manager made or approved becomes a
    pending placement request, which a manager of that eenheid decides.
    Placements from authoritative imports (ROO, kabinet, TK, ABD) and in
    external organisations are kept.
    """
    from bouwmeester.services.notification_service import NotificationService

    today = date.today()
    placements = (
        await db.scalars(
            select(PersonOrganisatieEenheid).where(
                PersonOrganisatieEenheid.person_id == person.id,
                PersonOrganisatieEenheid.bron == _UNCONFIRMED_PLACEMENT_BRON,
                (PersonOrganisatieEenheid.eind_datum.is_(None))
                | (PersonOrganisatieEenheid.eind_datum >= today),
            )
        )
    ).all()
    pending = set(
        (
            await db.scalars(
                select(OrgPlacementRequest.organisatie_eenheid_id).where(
                    OrgPlacementRequest.person_id == person.id,
                    OrgPlacementRequest.status == "pending",
                )
            )
        ).all()
    )
    for placement in placements:
        eenheid_id = placement.organisatie_eenheid_id
        if not await touches_organisation(db, eenheid_id):
            continue
        await db.delete(placement)
        if eenheid_id in pending:
            continue
        pending.add(eenheid_id)
        db.add(
            OrgPlacementRequest(
                person_id=person.id,
                organisatie_eenheid_id=eenheid_id,
                dienstverband=placement.dienstverband,
            )
        )
        eenheid_naam = await db.scalar(
            select(OrganisatieEenheid.naam).where(OrganisatieEenheid.id == eenheid_id)
        )
        await NotificationService(db).notify_placement_request(
            person_naam=person.naam,
            eenheid_id=eenheid_id,
            eenheid_naam=eenheid_naam or "",
        )
    await db.flush()


async def _who_decides(db: AsyncSession, eenheid: OrganisatieEenheid) -> str:
    """A sentence naming whom to ask about members of *eenheid*."""
    ids = await member_manager_ids(db, eenheid.id)
    names = sorted(
        (await db.scalars(select(Person.naam).where(Person.id.in_(ids)))).all()
    )
    if not names:
        return "Vraag het aan een systeembeheerder."
    if len(names) == 1:
        return f"Vraag het aan {names[0]}."
    return f"Vraag het aan {', '.join(names[:-1])} of {names[-1]}."


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
    all their ancestors.  So when an internal eenheid is involved (before or
    after, the eenheid itself or anything below it), the caller must manage
    the eenheid itself and the new parent.  Detaching into a new root is
    super_admin-only.

    An external eenheid (without internal parts) moves like it is created
    (``core.authz``): freely outside the internal organisation, and inside
    it only with ``org:create`` on the parent, both the one it leaves and
    the one it goes to.
    """
    if perm_ctx.is_super_admin:
        return
    if new_parent_id == eenheid.parent_id and new_type == eenheid.type:
        return
    internal = {eenheid.type, new_type} & INTERNAL_EENHEID_TYPES
    if not internal and not await _has_internal_descendant(db, eenheid.id):
        if new_parent_id == eenheid.parent_id:
            return
        for parent_id in (eenheid.parent_id, new_parent_id):
            await require(
                db,
                perm_ctx,
                "org:create",
                "organisatie_eenheid",
                place={"parent_id": parent_id, "type": new_type},
            )
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
    target_person_id: UUID | None,
) -> None:
    """Guard granting *role* to a person: authority, and never to yourself.

    ``target_person_id=None`` asks about someone else (for the frontend).
    """
    if (
        not perm_ctx.is_super_admin
        and target_person_id is not None
        and target_person_id == perm_ctx.person_id
    ):
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
    """Guard naming a manager when creating an eenheid.

    Where the eenheid may go is ``core.authz`` (``org:create``): inside the
    internal organisation on its parent, outside it anywhere.  A new
    eenheid has no members, so it grants nobody anything.  Naming a manager
    does, and the new eenheid inherits its parent's rights, so the parent
    decides.
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


async def _trusted_placement_eenheid_ids(
    db: AsyncSession, person_id: UUID
) -> set[UUID]:
    """Eenheden where a placement of *person_id* grants access at first login.

    Current and future placements in or below the internal organisation that
    a manager made or an import brought: ``hold_unconfirmed_placements``
    keeps exactly these when a contact becomes an account.
    """
    today = date.today()
    eenheid_ids = set(
        (
            await db.scalars(
                select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
                    PersonOrganisatieEenheid.person_id == person_id,
                    PersonOrganisatieEenheid.bron != _UNCONFIRMED_PLACEMENT_BRON,
                    (PersonOrganisatieEenheid.eind_datum.is_(None))
                    | (PersonOrganisatieEenheid.eind_datum >= today),
                )
            )
        ).all()
    )
    return {eid for eid in eenheid_ids if await touches_organisation(db, eid)}


_IDENTITY_REFUSAL = (
    "Deze persoon heeft al toegang via een plaatsing of rol. Alleen wie die "
    "toegang zelf kan geven, of een systeembeheerder, wijzigt de e-mailadressen."
)


async def _require_identity_authority(
    db: AsyncSession, perm_ctx: PermissionContext, person: Person
) -> None:
    """Guard the emails of a contact that already holds access.

    The first login with a verified email links to the record and takes
    over what it holds: trusted placements (a new hire placed by a manager)
    and resource grants.  Adding an email is therefore handing all of that
    to whoever controls the address, so the caller must be able to hand it
    out themselves: manage the members of every such eenheid, and hold the
    grant authority over every grant.  A contact holding nothing (a
    counterpart at a gemeente) stays open to ``people:update``.
    """
    for eenheid_id in await _trusted_placement_eenheid_ids(db, person.id):
        if not await can_manage_members(db, perm_ctx, eenheid_id):
            raise _forbidden(_IDENTITY_REFUSAL)
    grants = (
        await db.scalars(
            select(ResourcePermission).where(ResourcePermission.person_id == person.id)
        )
    ).all()
    for grant in grants:
        try:
            await _require_grant_authority(
                db,
                perm_ctx,
                resource_type=grant.resource_type,
                resource_id=grant.resource_id,
                rols=frozenset({grant.rol}),
                target_person_id=person.id,
                target_eenheid_id=None,
            )
        except HTTPException as exc:
            if exc.status_code not in (
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ):
                raise
            raise _forbidden(_IDENTITY_REFUSAL) from exc


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
    with ``people:update``, except the emails of a contact that already
    holds access (``_require_identity_authority``).

    The naam is not identity: a login links to a person by verified email
    only (``core.auth.get_or_create_person``).
    """
    if perm_ctx.is_super_admin or person.id == perm_ctx.person_id:
        return
    if not await is_account(db, person):
        if not perm_ctx.has_permission("people:update"):
            raise _forbidden("Onvoldoende rechten")
        if identity:
            await _require_identity_authority(db, perm_ctx, person)
        return
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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

    An eenheid grant counts for every member placed directly in that
    eenheid, as in ``core.authz`` (resource roles, step 2), so membership of
    a sub-eenheid does not count.  Nobody places themselves
    (``require_can_place``), so the eenheden that can reach the caller are
    those they are placed in now, will be placed in (a future start date),
    or asked to join (a pending request: whoever approves it decides about
    the membership, not about this grant).
    """
    if perm_ctx.person_id is None:
        return False
    if target_person_id is not None:
        return target_person_id == perm_ctx.person_id
    if target_eenheid_id is not None:
        return target_eenheid_id in await _joined_or_joining_ids(db, perm_ctx.person_id)
    return False


async def _joined_or_joining_ids(db: AsyncSession, person_id: UUID) -> set[UUID]:
    """Eenheden *person_id* is placed in, will be placed in, or asked to join."""
    today = date.today()
    placed = await db.scalars(
        select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
            PersonOrganisatieEenheid.person_id == person_id,
            (PersonOrganisatieEenheid.eind_datum.is_(None))
            | (PersonOrganisatieEenheid.eind_datum >= today),
        )
    )
    requested = await db.scalars(
        select(OrgPlacementRequest.organisatie_eenheid_id).where(
            OrgPlacementRequest.person_id == person_id,
            OrgPlacementRequest.status == "pending",
        )
    )
    return set(placed.all()) | set(requested.all())


# The permission that lets someone hand out roles on a resource.  Leads have
# no eigenaar: whoever may edit the lead keeps its roles current.
_GRANT_PERMISSION = {"lead": "lead:update"}

# Resource types that often live in no eenheid (corpus nodes; opdrachten,
# because FCC does not fill one).  There, registering yourself as a contact
# is allowed, see ``_may_register_self``.
_UNSCOPED_CONTACT_TYPES = frozenset({"corpus_node", "opdracht"})


def grant_permission(resource_type: str) -> str:
    """The permission that decides who hands out roles on *resource_type*."""
    return _GRANT_PERMISSION.get(resource_type, "resource_permission:manage")


def _rol_permissions(resource_type: str, rols: frozenset[str]) -> set[str]:
    type_roles = RESOURCE_ROLE_PERMISSIONS.get(resource_type, {})
    return set().union(*(type_roles.get(rol, set()) for rol in rols))


async def _may_register_self(
    db: AsyncSession, resource_type: str, resource_id: UUID, rols: frozenset[str]
) -> bool:
    """True if a grant of *rols* to yourself is a contact registration.

    Never a rol that carries grant authority (eigenaar, opdrachtgever): that
    would be taking control.  Other rols only on a lead (it has no eigenaar)
    or on a corpus node or opdracht without an eenheid, where the rights are
    tenant-wide anyway.  The grant never exceeds what the caller holds.
    """
    if grant_permission(resource_type) in _rol_permissions(resource_type, rols):
        return False
    if resource_type in _GRANT_PERMISSION:
        return True
    if resource_type not in _UNSCOPED_CONTACT_TYPES:
        return False
    _, eenheid_ids = await get_eenheid_ids(db, resource_type, resource_id)
    return not eenheid_ids


async def _require_grant_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    resource_type: str,
    resource_id: UUID,
    rols: frozenset[str],
    target_person_id: UUID | None,
    target_eenheid_id: UUID | None,
) -> None:
    """Authority to hand out (or change) *rols* on a resource.

    ``core.authz`` decides the rights, with the same rules as any other
    action on the resource (resource roles, rights on its eenheid, the
    tenant-wide fallback for unscoped nodes and opdrachten):

    - the caller must hold the grant permission on the resource
      (``resource_permission:manage``, for leads ``lead:update``);
    - a grant never exceeds what the grantor holds: every permission the
      rols give must be the caller's on this resource too, so an editor
      cannot make a colleague eigenaar (``node:delete``);
    - the grant must not reach the caller (directly or through an eenheid
      they are placed in), except a contact registration
      (``_may_register_self``).
    """
    if perm_ctx.is_super_admin:
        return
    await require(
        db, perm_ctx, grant_permission(resource_type), resource_type, resource_id
    )
    for perm in sorted(_rol_permissions(resource_type, rols)):
        if not await can(db, perm_ctx, perm, resource_type, resource_id):
            raise _forbidden(
                "Je kunt geen rol toekennen die meer rechten geeft dan je hier "
                "zelf hebt"
            )
    if await _grant_reaches_caller(
        db,
        perm_ctx,
        target_person_id=target_person_id,
        target_eenheid_id=target_eenheid_id,
    ) and not await _may_register_self(db, resource_type, resource_id, rols):
        raise _forbidden("Je kunt jezelf geen rol op dit item geven")


async def _share_source_eenheden(
    db: AsyncSession, source_eenheid_id: UUID | None, source_node_id: UUID | None
) -> list[UUID | None]:
    """The eenheden a share gives away; ``[None]`` for a tenant-wide source."""
    eenheid_ids: list[UUID | None] = [source_eenheid_id] if source_eenheid_id else []
    if source_node_id is not None:
        node = await db.get(CorpusNode, source_node_id)
        if node is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item niet gevonden")
        if node.organisatie_eenheid_id:
            eenheid_ids.append(node.organisatie_eenheid_id)
    return eenheid_ids or [None]


async def require_can_share(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    source_eenheid_id: UUID | None,
    source_node_id: UUID | None,
    target_eenheid_id: UUID | None,
) -> None:
    """Guard creating (``target_eenheid_id``) or revoking (``None``) a share.

    A share is a grant: the members of the target see the source, and with
    an edit share work on it with the rights they hold in the target.  So
    it needs ``org:manage`` on every eenheid it gives away (seeing an
    eenheid is not enough, or a team member could share its whole
    directorate onward; without an eenheid, system roles decide).  Creating
    one must not reach the caller: nobody shares with an eenheid they are
    in or are joining (``_grant_reaches_caller``).  Revoking only takes
    access away.
    """
    for eenheid_id in await _share_source_eenheden(
        db, source_eenheid_id, source_node_id
    ):
        await require(db, perm_ctx, "org:manage", "organisatie_eenheid", eenheid_id)
    if (
        target_eenheid_id is not None
        and not perm_ctx.is_super_admin
        and await _grant_reaches_caller(
            db, perm_ctx, target_person_id=None, target_eenheid_id=target_eenheid_id
        )
    ):
        raise _forbidden("Je kunt niet delen met een eenheid waar je zelf in zit")


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


async def require_can_name_first_owner(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    node_id: UUID,
    target_person_id: UUID,
) -> None:
    """Guard naming the first eigenaar of a node that has none (a review).

    Naming who owns a freshly imported parliamentary item is the point of
    reviewing it, so whoever may review it (``parlementair:review`` on the
    node) may do so.  Naming yourself is only allowed when you already edit
    the node (``node:update``): a reviewer without it would otherwise hand
    themselves rights.  Once the node has an eigenaar, changing that is a
    grant like any other.
    """
    has_owner = await db.scalar(
        select(ResourcePermission.id)
        .where(
            ResourcePermission.resource_type == "corpus_node",
            ResourcePermission.resource_id == node_id,
            ResourcePermission.rol == "eigenaar",
        )
        .limit(1)
    )
    if has_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dit item heeft al een eigenaar",
        )
    await require(db, perm_ctx, "parlementair:review", "corpus_node", node_id)
    if (
        not perm_ctx.is_super_admin
        and target_person_id == perm_ctx.person_id
        and not await can(db, perm_ctx, "node:update", "corpus_node", node_id)
    ):
        raise _forbidden(
            "Je kunt jezelf alleen eigenaar maken van een item dat je al mag bewerken"
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
        rols=frozenset({rol}),
        target_person_id=target_person_id,
        target_eenheid_id=target_eenheid_id,
    )


async def require_can_change_grants(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    resource_type: str,
    resource_id: UUID,
    person_id: UUID | None = None,
    eenheid_id: UUID | None = None,
    new_rol: str | None,
) -> None:
    """Guard changing or removing every grant of a person or eenheid on a resource.

    For routes that address a grant by (resource, person) or (resource,
    eenheid) rather than by its id.
    """
    from bouwmeester.repositories.resource_permission import (
        ResourcePermissionRepository,
    )

    grants = await ResourcePermissionRepository(db).find_grants(
        resource_type, resource_id, person_id=person_id, eenheid_id=eenheid_id
    )
    for grant in grants:
        await require_can_change_resource_role(db, perm_ctx, grant, new_rol=new_rol)


async def require_can_change_resource_role(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    grant: ResourcePermission,
    *,
    new_rol: str | None,
) -> None:
    """Guard changing (``new_rol``) or removing (``None``) an existing grant.

    A resource never loses its last eigenaar this way (409).  Otherwise
    giving up rights yourself (leaving, or stepping down to a rol that gives
    no more) is always allowed; anything else needs the authority to hand
    out both the current and the new rol.  The evaluation endpoint asks this
    as ``resource_role:revoke`` on the grant.
    """
    await _require_keeps_an_owner(db, grant, new_rol)
    if new_rol is not None:
        _require_known_rol(grant.resource_type, new_rol)
    if grant.person_id is not None and grant.person_id == perm_ctx.person_id:
        kept = _rol_permissions(
            grant.resource_type, frozenset({new_rol} if new_rol else set())
        )
        if kept <= _rol_permissions(grant.resource_type, frozenset({grant.rol})):
            return
    await _require_grant_authority(
        db,
        perm_ctx,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        rols=frozenset(r for r in (grant.rol, new_rol) if r is not None),
        target_person_id=grant.person_id,
        target_eenheid_id=grant.organisatie_eenheid_id,
    )
