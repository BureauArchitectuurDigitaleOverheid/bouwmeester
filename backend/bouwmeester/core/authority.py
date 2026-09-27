"""Authority over grants: who may change who has access to what.

Placements, managers, moving an eenheid, roles, identity, resource roles
and shares are decided by the guards here, built on ``core.authz`` (see
its module docstring for the model).  Seeing an eenheid never implies
authority over it.  Handing an agent power is super_admin's
(``services.agent_rules``); taking it away is not restricted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import (
    EenheidRights,
    can,
    eenheid_ids_where,
    get_eenheid_ids,
    perm_ctx_for,
    require,
    rights_on_eenheid,
)
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.core.resource_roles import RESOURCE_ROLE_PERMISSIONS
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import (
    INTERNAL_EENHEID_TYPES,
    OrganisatieEenheid,
)
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import (
    PLACEMENT_BRON_DETACHERING,
    PLACEMENT_BRON_HANDMATIG,
    PLACEMENT_BRON_LEIDINGGEVENDE,
    TRUSTED_PLACEMENT_BRONNEN,
    PersonOrganisatieEenheid,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole, Role
from bouwmeester.models.task import Task
from bouwmeester.repositories.org_tree import (
    eenheid_references,
    get_internal_ids,
    get_membership_ids,
    get_self_and_ancestor_ids,
    get_subtree_ids,
    get_touching_ids,
    placement_not_ended,
    placement_trusted,
    touches_organisation,
)
from bouwmeester.services.agent_rules import require_may_instruct

# Roles that make someone responsible for the members of an eenheid (and
# of everything below it).
MEMBER_MANAGER_ROLES = frozenset({"unit_manager", "ministry_admin"})


def _role_not_ended():
    """SQL: the role assignment has not ended (it may still have to start)."""
    today = date.today()
    return (PersonRole.eind_datum.is_(None)) | (PersonRole.eind_datum >= today)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def _require_may_empower(
    db: AsyncSession, perm_ctx: PermissionContext, target: Person | UUID | None
) -> None:
    """403 unless the caller may hand *target* power (an agent: super_admin)."""
    if isinstance(target, UUID):
        target = await db.get(Person, target)
    require_may_instruct(perm_ctx, target)


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


async def can_confirm_members(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid_id: UUID,
) -> bool:
    """True if the person decides who is a (trusted) member of *eenheid_id*.

    A manager of it or above it; outside the organisation (usually without
    a manager) also whoever holds ``org:manage`` there, typically its eigenaar.
    """
    if await can_manage_members(db, perm_ctx, eenheid_id):
        return True
    return not await touches_organisation(db, eenheid_id) and await can(
        db, perm_ctx, "org:manage", "organisatie_eenheid", eenheid_id
    )


async def confirmable_eenheid_ids(
    db: AsyncSession, perm_ctx: PermissionContext
) -> set[UUID] | None:
    """Every eenheid where ``can_confirm_members`` holds; ``None`` means all."""
    managed = await managed_subtree_ids(db, perm_ctx)
    owned = await eenheid_ids_where(db, perm_ctx, "org:manage")
    if managed is None or owned is None:
        return None
    return managed | {eid for eid in owned if not await touches_organisation(db, eid)}


async def member_manager_ids(db: AsyncSession, eenheid_id: UUID) -> set[UUID]:
    """The people ``can_confirm_members`` lets through, system roles aside."""
    chain = await get_self_and_ancestor_ids(db, eenheid_id)
    today = date.today()
    result = await db.execute(
        select(PersonRole.person_id).where(
            PersonRole.organisatie_eenheid_id.in_(chain),
            PersonRole.role_id.in_(MEMBER_MANAGER_ROLES),
            PersonRole.start_datum <= today,
            _role_not_ended(),
        )
    )
    ids = set(result.scalars().all())
    if not await touches_organisation(db, eenheid_id):
        owners = await db.scalars(
            select(ResourcePermission.person_id).where(
                ResourcePermission.resource_type == "organisatie_eenheid",
                ResourcePermission.resource_id.in_(chain),
                ResourcePermission.rol == "eigenaar",
                ResourcePermission.person_id.isnot(None),
            )
        )
        ids |= set(owners.all())
    return ids


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
    """True for a login, an agent or a role holder; False for a contact."""
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
    bron: str | None = None,
) -> None:
    """Guard creating, changing or ending a placement of *person* in *eenheid*.

    Needs ``people:update``.  An account's placement grants access, so only
    ``can_confirm_members`` places one (everyone else files a request);
    nobody places themselves, ending your own is always allowed.  Placing a
    contact is contact administration (informational, see ``core.authz``).
    Ending someone else's trusted placement (*bron*) needs
    ``can_confirm_members`` too.

    ``person=None`` asks about someone else: another account, or a contact
    with ``contact=True``.
    """
    if not perm_ctx.is_authenticated:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Niet ingelogd")
    if not perm_ctx.has_permission("people:update"):
        raise _forbidden("Onvoldoende rechten")
    own = person is not None and person.id == perm_ctx.person_id
    if own and ending:
        return
    if not ending:
        await _require_may_empower(db, perm_ctx, person)
    if own and not perm_ctx.is_super_admin:
        raise _forbidden(
            f"Je kunt jezelf niet in {eenheid.naam} plaatsen. Dien een "
            "plaatsingsverzoek in; een leidinggevende beslist."
        )
    if await can_confirm_members(db, perm_ctx, eenheid.id):
        return
    if ending and bron in TRUSTED_PLACEMENT_BRONNEN:
        raise _forbidden(
            "Deze plaatsing is bevestigd door een leidinggevende of komt uit een "
            "officiële bron. Alleen wie over de leden van "
            f"{eenheid.naam} beslist, kan hem beëindigen."
        )
    if contact if person is None else not await is_account(db, person):
        return
    if person is not None and await _is_detachering(db, perm_ctx, person, eenheid):
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


async def require_can_change_placement(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    placement: PersonOrganisatieEenheid,
    *,
    ending: bool,
) -> tuple[Person, OrganisatieEenheid]:
    """``require_can_place`` for an existing placement, knowing its bron; 404.

    The one guard for changing, ending and deleting a placement, and for the
    evaluation ``person:place`` with ``placement_id``.
    """
    person = await db.get(Person, placement.person_id)
    eenheid = await db.get(OrganisatieEenheid, placement.organisatie_eenheid_id)
    if person is None or eenheid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plaatsing niet gevonden")
    await require_can_place(
        db, perm_ctx, person, eenheid, ending=ending, bron=placement.bron
    )
    return person, eenheid


async def _is_detachering(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
    eenheid: OrganisatieEenheid,
) -> bool:
    """True if the caller links own staff to an external organisation.

    Informational only: bron ``detachering`` is never trusted.
    """
    return (
        eenheid.type not in INTERNAL_EENHEID_TYPES
        and not await touches_organisation(db, eenheid.id)
        and await _manages_person(db, perm_ctx, person)
    )


async def placement_bron(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
    eenheid: OrganisatieEenheid,
) -> str:
    """The bron to record for a placement the caller makes (or changes).

    Trusted only from ``can_confirm_members``; otherwise a detachering or
    contact administration, neither of which gives access.
    """
    if await can_confirm_members(db, perm_ctx, eenheid.id):
        return PLACEMENT_BRON_LEIDINGGEVENDE
    if await _is_detachering(db, perm_ctx, person, eenheid):
        return PLACEMENT_BRON_DETACHERING
    return PLACEMENT_BRON_HANDMATIG


async def bron_after_change(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
    eenheid: OrganisatieEenheid,
    bron: str,
) -> str:
    """The bron of a placement after the caller changes or reopens it.

    A trusted one stays trusted only for ``can_confirm_members``; otherwise
    a manager's becomes ``placement_bron`` and a sync's is refused (403).
    """
    if bron not in TRUSTED_PLACEMENT_BRONNEN:
        return bron
    if await can_confirm_members(db, perm_ctx, eenheid.id):
        return bron
    if bron != PLACEMENT_BRON_LEIDINGGEVENDE:
        raise _forbidden(
            "Deze plaatsing komt uit een officiële bron. Alleen wie over de "
            f"leden van {eenheid.naam} beslist, wijzigt of heropent hem."
        )
    return await placement_bron(db, perm_ctx, person, eenheid)


async def approve_placement_requests(
    db: AsyncSession,
    *,
    person_id: UUID,
    eenheid_id: UUID,
    decided_by: UUID | None,
) -> list[OrgPlacementRequest]:
    """Approve every pending request of *person_id* for *eenheid_id*.

    Called once the placement is trusted; the requester is notified once.
    """
    from bouwmeester.schema.notification import NotificationCreate
    from bouwmeester.services.notification_service import NotificationService

    requests = list(
        (
            await db.scalars(
                select(OrgPlacementRequest).where(
                    OrgPlacementRequest.person_id == person_id,
                    OrgPlacementRequest.organisatie_eenheid_id == eenheid_id,
                    OrgPlacementRequest.status == "pending",
                )
            )
        ).all()
    )
    if not requests:
        return []
    now = datetime.now(UTC)
    for req in requests:
        req.status = "approved"
        req.decided_at = now
        req.decided_by = decided_by
    await db.flush()
    eenheid_naam = (
        await db.scalar(
            select(OrganisatieEenheid.naam).where(OrganisatieEenheid.id == eenheid_id)
        )
        or ""
    )
    await NotificationService(db).send(
        NotificationCreate(
            person_id=person_id,
            type="placement_approved",
            title=f"Toegevoegd aan: {eenheid_naam}",
            message=f"Je bent toegevoegd aan '{eenheid_naam}'.",
        )
    )
    return requests


async def hold_unconfirmed_placements(db: AsyncSession, person: Person) -> None:
    """Turn contact placements into requests when a contact becomes an account.

    Its active ``handmatig`` placements that touch the organisation become
    pending requests a manager confirms; everything else is kept.
    """
    placements = (
        await db.scalars(
            select(PersonOrganisatieEenheid).where(
                PersonOrganisatieEenheid.person_id == person.id,
                PersonOrganisatieEenheid.bron == PLACEMENT_BRON_HANDMATIG,
                placement_not_ended(),
            )
        )
    ).all()
    touching = await get_touching_ids(
        db, [p.organisatie_eenheid_id for p in placements]
    )
    await _placements_to_requests(
        db, person, [p for p in placements if p.organisatie_eenheid_id in touching]
    )


async def _placements_to_requests(
    db: AsyncSession, person: Person, placements: list[PersonOrganisatieEenheid]
) -> None:
    """Replace *placements* by pending requests, one per eenheid; notify."""
    from bouwmeester.services.notification_service import NotificationService

    if not placements:
        return
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


async def unconfirm_placements(
    db: AsyncSession, placements: list[PersonOrganisatieEenheid]
) -> int:
    """Take the trust away from *placements*; returns how many.

    An account's become pending requests, a contact's become ``handmatig``.
    """
    by_person: dict[UUID, list[PersonOrganisatieEenheid]] = {}
    for placement in placements:
        by_person.setdefault(placement.person_id, []).append(placement)
    for person_id, own in by_person.items():
        person = await db.get(Person, person_id)
        if person is None:
            continue
        if await is_account(db, person):
            await _placements_to_requests(db, person, own)
            continue
        for placement in own:
            duplicate = await db.scalar(
                select(PersonOrganisatieEenheid.id).where(
                    PersonOrganisatieEenheid.person_id == person_id,
                    PersonOrganisatieEenheid.organisatie_eenheid_id
                    == placement.organisatie_eenheid_id,
                    PersonOrganisatieEenheid.bron == PLACEMENT_BRON_HANDMATIG,
                    PersonOrganisatieEenheid.id != placement.id,
                    placement_not_ended(),
                )
            )
            if duplicate is not None:
                await db.delete(placement)
            else:
                placement.bron = PLACEMENT_BRON_HANDMATIG
    await db.flush()
    return len(placements)


async def hold_access_of_unproven_login(
    db: AsyncSession, person: Person, email: str
) -> bool:
    """Hold what a contact holds when its first login uses an unproven address.

    ``_require_identity_authority`` guards adding an address to a contact
    that holds access, but not one added before that access was handed
    out.  So at the first login the address counts as proven only when
    nobody recorded who added it (older rows, syncs, the admin seed) or
    whoever added it could hand out everything the record holds: decide
    about the members of every eenheid with a trusted placement or a role,
    and grant every person-level resource role.  Otherwise the trusted
    placements become pending requests, the roles end and the resource
    grants are removed, for whoever decides to hand them out again.
    Returns True when something was held.
    """
    added_by = await db.scalar(
        select(PersonEmail.added_by_id).where(
            func.lower(PersonEmail.email) == email.lower(),
            PersonEmail.person_id == person.id,
        )
    )
    if added_by is None or added_by == person.id:
        return False
    placements = list(
        (
            await db.scalars(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.person_id == person.id,
                    placement_trusted(),
                    placement_not_ended(),
                )
            )
        ).all()
    )
    roles = list(
        (
            await db.scalars(
                select(PersonRole).where(
                    PersonRole.person_id == person.id, _role_not_ended()
                )
            )
        ).all()
    )
    grants = list(
        (
            await db.scalars(
                select(ResourcePermission).where(
                    ResourcePermission.person_id == person.id
                )
            )
        ).all()
    )
    if not placements and not roles and not grants:
        return False
    adder = await perm_ctx_for(db, added_by)
    if adder.is_super_admin:
        return False
    eenheid_ids = {p.organisatie_eenheid_id for p in placements}
    eenheid_ids |= {r.organisatie_eenheid_id for r in roles}
    if await _may_hand_out(db, adder, eenheid_ids, grants):
        return False
    await _placements_to_requests(db, person, placements)
    for role in roles:
        role.eind_datum = date.today() - timedelta(days=1)
    for grant in grants:
        await db.delete(grant)
    await db.flush()
    return True


async def _may_hand_out(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid_ids: set[UUID | None],
    grants: list[ResourcePermission],
) -> bool:
    """Could *perm_ctx* confirm members of every eenheid and make every grant?"""
    if None in eenheid_ids:
        return False
    for eenheid_id in eenheid_ids:
        if not await can_confirm_members(db, perm_ctx, eenheid_id):
            return False
    for grant in grants:
        if not await _may_grant(db, perm_ctx, grant):
            return False
    return True


# ---------------------------------------------------------------------------
# Trust after a structural change
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustSnapshot:
    """Who decided about the members of a subtree, before it changes.

    Per eenheid with open manager placements: those placements, who could
    confirm them and whether it touched the organisation.
    """

    placement_ids: dict[UUID, frozenset[UUID]]
    confirmers: dict[UUID, frozenset[UUID]]
    touching: frozenset[UUID]


async def snapshot_trust(db: AsyncSession, eenheid_id: UUID) -> TrustSnapshot:
    """A ``TrustSnapshot`` of *eenheid_id* and everything below it."""
    subtree = await get_subtree_ids(db, [eenheid_id])
    rows = await db.execute(
        select(
            PersonOrganisatieEenheid.organisatie_eenheid_id,
            PersonOrganisatieEenheid.id,
        ).where(
            PersonOrganisatieEenheid.organisatie_eenheid_id.in_(subtree),
            PersonOrganisatieEenheid.bron == PLACEMENT_BRON_LEIDINGGEVENDE,
            placement_not_ended(),
        )
    )
    placements: dict[UUID, set[UUID]] = {}
    for eid, pid in rows.all():
        placements.setdefault(eid, set()).add(pid)
    return TrustSnapshot(
        placement_ids={eid: frozenset(ids) for eid, ids in placements.items()},
        confirmers={
            eid: frozenset(await member_manager_ids(db, eid)) for eid in placements
        },
        touching=frozenset(await get_touching_ids(db, list(placements))),
    )


async def distrust_lost_confirmations(
    db: AsyncSession,
    snapshot: TrustSnapshot,
    *,
    moved_into: dict[UUID, UUID] | None = None,
) -> int:
    """Unconfirm manager placements made by who no longer decides there.

    Per eenheid of *snapshot* (``moved_into`` maps a merged eenheid to its
    target): when it newly touches the organisation or lost one of its
    confirmers (placements do not record who confirmed them), all its
    placements are unconfirmed.  Returns how many.
    """
    moved_into = moved_into or {}
    now = {eid: moved_into.get(eid, eid) for eid in snapshot.placement_ids}
    touching_now = await get_touching_ids(db, list(set(now.values())))
    lost: list[UUID] = []
    for eid, ids in snapshot.placement_ids.items():
        joined = eid not in snapshot.touching and now[eid] in touching_now
        if joined or snapshot.confirmers[eid] - await member_manager_ids(db, now[eid]):
            lost.extend(ids)
    if not lost:
        return 0
    placements = (
        await db.scalars(
            select(PersonOrganisatieEenheid).where(
                PersonOrganisatieEenheid.id.in_(lost),
                PersonOrganisatieEenheid.bron == PLACEMENT_BRON_LEIDINGGEVENDE,
                placement_not_ended(),
            )
        )
    ).all()
    # A member who also holds a placement nobody lost the say over (the
    # target's own, after a merge) stays a member through that one.
    kept = set(
        (
            await db.execute(
                select(
                    PersonOrganisatieEenheid.person_id,
                    PersonOrganisatieEenheid.organisatie_eenheid_id,
                ).where(
                    PersonOrganisatieEenheid.person_id.in_(
                        {p.person_id for p in placements}
                    ),
                    PersonOrganisatieEenheid.id.not_in(lost),
                    placement_trusted(),
                    placement_not_ended(),
                )
            )
        ).all()
    )
    return await unconfirm_placements(
        db,
        [p for p in placements if (p.person_id, p.organisatie_eenheid_id) not in kept],
    )


async def drop_eenheid_owner_grants(db: AsyncSession, eenheid_ids: set[UUID]) -> int:
    """Remove every eigenaar grant on *eenheid_ids*; returns how many."""
    if not eenheid_ids:
        return 0
    result = await db.execute(
        delete(ResourcePermission).where(
            ResourcePermission.resource_type == "organisatie_eenheid",
            ResourcePermission.resource_id.in_(eenheid_ids),
            ResourcePermission.rol == "eigenaar",
        )
    )
    await db.flush()
    return result.rowcount or 0


async def joins_organisation(
    db: AsyncSession,
    eenheid: OrganisatieEenheid,
    *,
    new_parent_id: UUID | None,
    new_type: str,
) -> bool:
    """True if the change makes *eenheid* internal or newly touch the organisation."""
    internal = INTERNAL_EENHEID_TYPES
    if new_type in internal and eenheid.type not in internal:
        return True
    if await touches_organisation(db, eenheid.id):
        return False
    return new_parent_id is not None and await touches_organisation(db, new_parent_id)


async def bring_into_organisation(
    db: AsyncSession, eenheid_id: UUID, snapshot: TrustSnapshot
) -> tuple[int, int]:
    """After a change that ``joins_organisation``: managers decide now.

    Drops the eigenaar grants in the subtree and unconfirms what an
    eigenaar may have confirmed (*snapshot* taken before the change).
    Returns (eigenaar grants removed, placements unconfirmed).
    """
    owners = await drop_eenheid_owner_grants(
        db, await get_subtree_ids(db, [eenheid_id])
    )
    return owners, await distrust_lost_confirmations(db, snapshot)


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
    await _require_may_empower(db, perm_ctx, requester_id)
    if perm_ctx.is_super_admin:
        return
    if requester_id == perm_ctx.person_id:
        raise _forbidden("Je kunt niet over je eigen verzoek beslissen")
    if not await can_confirm_members(db, perm_ctx, eenheid_id):
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

    Needs ``org:update`` on it.  Ending up internal is placed like a new
    internal eenheid (``core.authz``).  With an internal eenheid involved
    (before, after or below), the caller manages the eenheid, the parent
    it leaves and the one it goes to; a new root is super_admin's.  An
    external eenheid moves like it is created (``org:create`` on both
    parents); taking it out of or into the organisation also needs a
    manager of the parent on the organisation's side.
    """
    if perm_ctx.is_super_admin:
        return
    await require(db, perm_ctx, "org:update", "organisatie_eenheid", eenheid.id)
    if new_parent_id == eenheid.parent_id and new_type == eenheid.type:
        return
    if (
        new_type != eenheid.type
        and new_type not in INTERNAL_EENHEID_TYPES
        and await _has_internal_descendant(db, eenheid.id)
    ):
        raise _forbidden(
            "Onder deze eenheid hangen interne eenheden. Alleen systeembeheerders "
            "maken er een externe organisatie van."
        )
    # A ministerie, before or after, is super_admin's (``core.authz``).
    kind = "ministerie" if "ministerie" in {eenheid.type, new_type} else new_type
    if kind in INTERNAL_EENHEID_TYPES:
        await require(
            db,
            perm_ctx,
            "org:create",
            "organisatie_eenheid",
            place={"parent_id": new_parent_id, "type": kind},
        )
    internal = {eenheid.type, new_type} & INTERNAL_EENHEID_TYPES
    if internal or await _has_internal_descendant(db, eenheid.id):
        await _require_internal_move(db, perm_ctx, eenheid, new_parent_id)
        return
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
    leaves = eenheid.parent_id is not None and await touches_organisation(
        db, eenheid.parent_id
    )
    stays = new_parent_id is not None and await touches_organisation(db, new_parent_id)
    if (
        leaves
        and not stays
        and not await can_manage_members(db, perm_ctx, eenheid.parent_id)
    ):
        raise _forbidden(
            "Alleen een leidinggevende van de bovenliggende eenheid haalt deze "
            "eenheid uit de organisatie"
        )
    if (
        stays
        and not leaves
        and not await can_manage_members(db, perm_ctx, new_parent_id)
    ):
        raise _forbidden(
            "Alleen een leidinggevende van de nieuwe bovenliggende eenheid haalt "
            "deze eenheid de organisatie in"
        )


async def _require_internal_move(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid: OrganisatieEenheid,
    new_parent_id: UUID | None,
) -> None:
    """``require_can_move_eenheid`` when an internal eenheid is involved."""
    if not await can_manage_members(db, perm_ctx, eenheid.id):
        raise _forbidden(
            "Alleen een leidinggevende van deze eenheid kan hem verplaatsen "
            "of van soort veranderen"
        )
    if new_parent_id == eenheid.parent_id:
        return
    if new_parent_id is None:
        raise _forbidden("Alleen systeembeheerders maken een losse eenheid")
    if eenheid.parent_id is not None and not await can_manage_members(
        db, perm_ctx, eenheid.parent_id
    ):
        raise _forbidden(
            "Alleen een leidinggevende van de huidige bovenliggende eenheid kan "
            "deze eenheid daar weghalen"
        )
    if not await can_manage_members(db, perm_ctx, new_parent_id):
        raise _forbidden(
            "Alleen een leidinggevende van de nieuwe bovenliggende eenheid kan "
            "hier een eenheid onder hangen"
        )


async def require_can_dissolve_eenheid(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    eenheid: OrganisatieEenheid,
) -> None:
    """Guard dissolving an eenheid (``geldig_tot``), which ends its roles
    and placements.

    An internal one only by who manages it.  While someone else holds a
    trusted placement or a role there: ``can_confirm_members``, plus
    ``require_can_revoke_role`` for each role ranked at or above the caller's.
    """
    if perm_ctx.is_super_admin:
        return
    if eenheid.type in INTERNAL_EENHEID_TYPES and not await can_manage_members(
        db, perm_ctx, eenheid.id
    ):
        raise _forbidden("Alleen een leidinggevende kan deze eenheid opheffen")
    roles = (
        await db.scalars(
            select(PersonRole).where(
                PersonRole.organisatie_eenheid_id == eenheid.id,
                _role_not_ended(),
            )
        )
    ).all()
    others = [r for r in roles if r.person_id != perm_ctx.person_id]
    trusted_member = await db.scalar(
        select(PersonOrganisatieEenheid.id)
        .where(
            PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid.id,
            PersonOrganisatieEenheid.person_id != perm_ctx.person_id,
            placement_trusted(),
            placement_not_ended(),
        )
        .limit(1)
    )
    if not others and trusted_member is None:
        return
    if not await can_confirm_members(db, perm_ctx, eenheid.id):
        raise _forbidden(
            "Alleen wie over de leden van deze eenheid beslist, heft hem op "
            "zolang er mensen in geplaatst zijn of rollen op hebben"
        )
    rights = await rights_on_eenheid(
        db, perm_ctx, eenheid.id, include_system_roles=False
    )
    own_rank = await _role_rank(db, set(rights.roles))
    for assignment in others:
        if await _role_rank(db, {assignment.role_id}) >= own_rank:
            await require_can_revoke_role(db, perm_ctx, assignment)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


async def _role_rank(db: AsyncSession, role_ids: set[str]) -> int:
    if not role_ids:
        return 0
    ranks = await db.scalars(select(Role.rank).where(Role.id.in_(role_ids)))
    return max(ranks, default=0)


async def _assign_role_rights(
    db: AsyncSession, perm_ctx: PermissionContext, eenheid_id: UUID
) -> EenheidRights:
    """The caller's organisational rights on *eenheid_id* if they include
    ``people:assign_role`` (platform_admin does not staff the organisation); 403.
    """
    rights = await rights_on_eenheid(
        db, perm_ctx, eenheid_id, include_system_roles=False
    )
    if not rights.has("people:assign_role"):
        raise _forbidden("Geen bevoegdheid om rollen toe te kennen in deze eenheid")
    return rights


async def require_can_assign_roles_in(
    db: AsyncSession, perm_ctx: PermissionContext, eenheid_id: UUID
) -> None:
    """Guard seeing and handling the role assignments of *eenheid_id*."""
    await _assign_role_rights(db, perm_ctx, eenheid_id)


async def _require_role_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    role: Role,
    eenheid_id: UUID | None,
) -> None:
    """Guard granting or revoking *role* on *eenheid_id*, whoever it is for.

    System roles are super_admin's; otherwise ``_assign_role_rights`` and
    *role* must rank below the caller's highest role there.
    """
    if perm_ctx.is_super_admin:
        return
    if eenheid_id is None:
        raise _forbidden("Alleen systeembeheerders kennen systeemrollen toe")
    rights = await _assign_role_rights(db, perm_ctx, eenheid_id)
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
    await _require_may_empower(db, perm_ctx, target_person_id)
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
    """Guard naming or clearing the manager: assigning ``unit_manager``."""
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
    """Guard naming a manager when creating an eenheid (where it goes is
    ``core.authz``): decided on the parent, whose rights it inherits.
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
    """Eenheden where *person_id* holds a trusted placement: past, current or
    future (an ended one can be reopened for whoever takes over the record).
    """
    return set(
        (
            await db.scalars(
                select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
                    PersonOrganisatieEenheid.person_id == person_id,
                    placement_trusted(),
                )
            )
        ).all()
    )


async def _membership_reaches(db: AsyncSession, eenheid_id: UUID) -> bool:
    """True if membership of *eenheid_id* gives access to anything: always
    for an internal eenheid, else only when something hangs on it.
    """
    if await get_internal_ids(db, [eenheid_id]):
        return True
    return bool(await eenheid_references(db, eenheid_id))


_IDENTITY_REFUSAL = (
    "Deze persoon heeft al toegang via een plaatsing, rol of taak. Alleen wie die "
    "toegang zelf kan geven, of een systeembeheerder, wijzigt de e-mailadressen."
)


async def _require_identity_authority(
    db: AsyncSession, perm_ctx: PermissionContext, person: Person
) -> None:
    """Guard the emails of a contact that already holds access.

    A first login takes over the record's trusted placements, resource
    grants and assigned tasks, so adding an address hands those out: the
    caller must confirm the members of every such eenheid, hold the grant
    authority over every grant and ``task:update`` on every task.
    """
    for eenheid_id in await _trusted_placement_eenheid_ids(db, person.id):
        if await _membership_reaches(db, eenheid_id) and not await can_confirm_members(
            db, perm_ctx, eenheid_id
        ):
            raise _forbidden(_IDENTITY_REFUSAL)
    grants = (
        await db.scalars(
            select(ResourcePermission).where(ResourcePermission.person_id == person.id)
        )
    ).all()
    for grant in grants:
        if not await _may_grant(db, perm_ctx, grant):
            raise _forbidden(_IDENTITY_REFUSAL)
    task_ids = (
        await db.scalars(select(Task.id).where(Task.assignee_id == person.id))
    ).all()
    for task_id in task_ids:
        if not await can(db, perm_ctx, "task:update", "task", task_id):
            raise _forbidden(_IDENTITY_REFUSAL)


async def require_can_edit_person(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
    *,
    identity: bool,
) -> None:
    """Guard editing a person.

    ``identity`` (email addresses, which decide which login maps to whom):
    on an account only the person or a super_admin, on an agent only a
    super_admin.  Other fields also by a manager of one of the person's
    eenheden.  Contacts: anyone with ``people:update``, except the emails of
    one holding access (``_require_identity_authority``).
    """
    if perm_ctx.is_super_admin:
        return
    if identity and person.is_agent:
        raise _forbidden(
            "Alleen systeembeheerders wijzigen de identiteit van een agent"
        )
    if person.id == perm_ctx.person_id:
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


def require_can_read_person(perm_ctx: PermissionContext, person_id: UUID) -> None:
    """Guard reading a full person record: yourself always, others with people:read."""
    if not perm_ctx.is_authenticated:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Niet ingelogd")
    if person_id != perm_ctx.person_id and not perm_ctx.has_permission("people:read"):
        raise _forbidden("Onvoldoende rechten")


async def require_can_delete_person(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    person: Person,
) -> None:
    """Guard deleting a person: an account is super_admin's (it cascades to
    roles, placements and grants), a contact needs ``people:manage``.
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

    An eenheid grant reaches its direct members, including future and
    requested ones (``_joined_or_joining_ids``).
    """
    if perm_ctx.person_id is None:
        return False
    if target_person_id is not None:
        return target_person_id == perm_ctx.person_id
    if target_eenheid_id is not None:
        return target_eenheid_id in await _joined_or_joining_ids(db, perm_ctx.person_id)
    return False


async def _joined_or_joining_ids(db: AsyncSession, person_id: UUID) -> set[UUID]:
    """Eenheden *person_id* is placed in (trusted or not), will be placed in,
    or asked to join.
    """
    placed = await db.scalars(
        select(PersonOrganisatieEenheid.organisatie_eenheid_id).where(
            PersonOrganisatieEenheid.person_id == person_id,
            placement_not_ended(),
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

    Never a rol with grant authority; others only on a lead or on an
    unscoped node or opdracht, where the rights are tenant-wide anyway.
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

    The caller holds ``grant_permission`` there and every permission the
    rols give, and the grant does not reach the caller except as a contact
    registration (``_may_register_self``).
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


async def _may_grant(
    db: AsyncSession, perm_ctx: PermissionContext, grant: ResourcePermission
) -> bool:
    """Could *perm_ctx* hand out this existing grant (``_require_grant_authority``)?"""
    try:
        await _require_grant_authority(
            db,
            perm_ctx,
            resource_type=grant.resource_type,
            resource_id=grant.resource_id,
            rols=frozenset({grant.rol}),
            target_person_id=grant.person_id,
            target_eenheid_id=grant.organisatie_eenheid_id,
        )
    except HTTPException as exc:
        if exc.status_code not in (403, 404):
            raise
        return False
    return True


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

    A share is a grant: ``org:manage`` on every eenheid it gives away, and
    never to an eenheid the caller is in or joining.
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


async def _node_owner_grants(
    db: AsyncSession, node_id: UUID
) -> list[ResourcePermission]:
    return list(
        (
            await db.scalars(
                select(ResourcePermission).where(
                    ResourcePermission.resource_type == "corpus_node",
                    ResourcePermission.resource_id == node_id,
                    ResourcePermission.rol == "eigenaar",
                )
            )
        ).all()
    )


async def _require_first_owner_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    node_id: UUID,
    target_person_id: UUID,
) -> None:
    """Naming the first eigenaar of a node that has none (the reviewer's
    mandate): someone who reads the node, yourself only with ``node:update``.
    """
    if perm_ctx.is_super_admin:
        return
    if target_person_id == perm_ctx.person_id:
        if not await can(db, perm_ctx, "node:update", "corpus_node", node_id):
            raise _forbidden(
                "Je kunt jezelf alleen eigenaar maken van een item dat je al "
                "mag bewerken"
            )
        return
    target_ctx = await perm_ctx_for(db, target_person_id)
    if not await can(db, target_ctx, "node:read", "corpus_node", node_id):
        raise _forbidden(
            "Deze persoon kan dit item niet zien en kan er dus geen eigenaar van zijn"
        )


async def require_can_name_owner(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    node_id: UUID,
    target_person_id: UUID,
) -> None:
    """Guard making *target_person_id* the sole person eigenaar of a node.

    Needs ``parlementair:review``; then nothing (already eigenaar), the first
    eigenaar, or the authority to grant eigenaar and remove every current
    person eigenaar.
    """
    target = await db.get(Person, target_person_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Persoon niet gevonden")
    await require(db, perm_ctx, "parlementair:review", "corpus_node", node_id)
    await _require_may_empower(db, perm_ctx, target)
    grants = await _node_owner_grants(db, node_id)
    if any(grant.person_id == target_person_id for grant in grants):
        return
    if not grants:
        await _require_first_owner_authority(
            db, perm_ctx, node_id=node_id, target_person_id=target_person_id
        )
        return
    await require_can_grant_resource_role(
        db,
        perm_ctx,
        resource_type="corpus_node",
        resource_id=node_id,
        rol="eigenaar",
        target_person_id=target_person_id,
    )
    for grant in grants:
        if grant.person_id is not None:
            await _require_change_authority(db, perm_ctx, grant, new_rol=None)


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
    await _require_may_empower(db, perm_ctx, target_person_id)
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
    """Guard changing or removing every grant of a person or eenheid on a resource."""
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

    Giving up your own rights is always allowed; anything else needs the
    authority over both rols.  The last eigenaar stays (409), checked after
    authority so outsiders learn nothing about the owners.
    """
    await _require_change_authority(db, perm_ctx, grant, new_rol=new_rol)
    await _require_keeps_an_owner(db, grant, new_rol)


async def _require_change_authority(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    grant: ResourcePermission,
    *,
    new_rol: str | None,
) -> None:
    """Authority to change or remove *grant*, leaving the last-owner rule aside."""
    if new_rol is not None:
        _require_known_rol(grant.resource_type, new_rol)
        await _require_may_empower(db, perm_ctx, grant.person_id)
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
