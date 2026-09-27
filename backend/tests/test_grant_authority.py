"""Who may change who has access to what (``core/authority.py``).

Covers placing people in an eenheid, naming a manager, moving and
dissolving eenheden, assigning roles, deciding placement requests, editing
someone's identity, granting resource roles, tenant-wide admin actions, chat
write tools, and linking a login to an existing person.

Uses a realistic tree (ministerie > DG > directie > team, a sibling team
and an external gemeente) and real permission resolution: only the current
user is overridden, never the permission context.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import (
    get_optional_user,
    get_or_create_person,
    validate_bearer_token,
)
from bouwmeester.core.permissions import PermissionContext, get_admin_user
from bouwmeester.middleware.auth_required import is_public_path
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.notification import Notification
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole
from tests.factories import (
    client_as,
    grant_role,
    make_org,
    make_person,
    place,
)


@dataclass
class Tree:
    ministerie: OrganisatieEenheid
    dg: OrganisatieEenheid
    directie: OrganisatieEenheid
    team: OrganisatieEenheid
    sibling: OrganisatieEenheid
    gemeente: OrganisatieEenheid
    member: Person  # plain member of team (implicit viewer)
    editor: Person  # editor on team
    directie_manager: Person  # unit_manager on directie
    ministry_admin: Person  # ministry_admin on dg
    platform_admin: Person
    super_admin: Person
    contact: Person  # external contact, no account
    db: AsyncSession


@pytest.fixture
async def tree(db_session: AsyncSession) -> Tree:
    db = db_session
    ministerie = await make_org(db, "Ministerie", "ministerie")
    dg = await make_org(db, "DG", "directoraat_generaal", ministerie)
    directie = await make_org(db, "Directie", "directie", dg)
    team = await make_org(db, "Team", "team", directie)
    sibling = await make_org(db, "Ander team", "team", directie)
    gemeente = await make_org(db, "Gemeente", "gemeente")

    member = await make_person(db, "Lid")
    await place(db, member, team)

    editor = await make_person(db, "Redacteur")
    await place(db, editor, team)
    await grant_role(db, editor, "editor", team)

    directie_manager = await make_person(db, "Directeur")
    await place(db, directie_manager, directie)
    await grant_role(db, directie_manager, "unit_manager", directie)

    ministry_admin = await make_person(db, "DG-beheerder")
    await place(db, ministry_admin, dg)
    await grant_role(db, ministry_admin, "ministry_admin", dg)

    platform_admin = await make_person(db, "Platformbeheerder")
    await grant_role(db, platform_admin, "platform_admin")

    super_admin = await make_person(db, "Systeembeheerder")
    await grant_role(db, super_admin, "super_admin")

    contact = await make_person(db, "Contact", account=False)

    return Tree(
        ministerie=ministerie,
        dg=dg,
        directie=directie,
        team=team,
        sibling=sibling,
        gemeente=gemeente,
        member=member,
        editor=editor,
        directie_manager=directie_manager,
        ministry_admin=ministry_admin,
        platform_admin=platform_admin,
        super_admin=super_admin,
        contact=contact,
        db=db,
    )


def _placement(org: OrganisatieEenheid) -> dict:
    return {"organisatie_eenheid_id": str(org.id), "start_datum": str(date.today())}


async def _email_of(db: AsyncSession, person: Person) -> str:
    return await db.scalar(
        select(PersonEmail.email).where(PersonEmail.person_id == person.id)
    )


async def _placement_of(
    db: AsyncSession, person: Person, org: OrganisatieEenheid
) -> PersonOrganisatieEenheid:
    return await db.scalar(
        select(PersonOrganisatieEenheid).where(
            PersonOrganisatieEenheid.person_id == person.id,
            PersonOrganisatieEenheid.organisatie_eenheid_id == org.id,
        )
    )


# ---------------------------------------------------------------------------
# Placements
# ---------------------------------------------------------------------------


async def test_member_cannot_place_self_in_other_team(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
    assert resp.status_code == 403


async def test_editor_cannot_place_colleague_in_team(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
    assert resp.status_code == 403


async def test_member_cannot_end_someone_elses_placement(tree: Tree):
    placement = await _placement_of(tree.db, tree.editor, tree.team)
    async with client_as(tree.db, tree.member) as c:
        resp = await c.delete(
            f"/api/people/{tree.editor.id}/organisaties/{placement.id}"
        )
    assert resp.status_code == 403


async def test_member_ends_own_placement(tree: Tree):
    placement = await _placement_of(tree.db, tree.member, tree.team)
    async with client_as(tree.db, tree.member) as c:
        resp = await c.put(
            f"/api/people/{tree.member.id}/organisaties/{placement.id}",
            json={"eind_datum": str(date.today())},
        )
    assert resp.status_code == 200, resp.text


async def test_member_cannot_reopen_own_ended_placement(tree: Tree):
    placement = await _placement_of(tree.db, tree.member, tree.team)
    placement.eind_datum = date.today() - timedelta(days=1)
    await tree.db.flush()
    async with client_as(tree.db, tree.member) as c:
        later = await c.put(
            f"/api/people/{tree.member.id}/organisaties/{placement.id}",
            json={"eind_datum": str(date.today() + timedelta(days=365))},
        )
        open_ended = await c.put(
            f"/api/people/{tree.member.id}/organisaties/{placement.id}",
            json={"eind_datum": None},
        )
    assert later.status_code == 403
    assert open_ended.status_code == 403


async def test_manager_places_in_descendant_team(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
    assert resp.status_code == 201, resp.text


async def test_manager_cannot_place_outside_subtree(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.dg)
        )
    assert resp.status_code == 403


async def test_manager_cannot_place_self_below(tree: Tree):
    """Nobody grants themselves anything, a manager neither."""
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.directie_manager.id}/organisaties",
            json=_placement(tree.team),
        )
    assert resp.status_code == 403


async def test_placing_someone_unnamed_is_a_managers_call(tree: Tree):
    """``person=None`` asks about another account without revealing anyone's."""
    from bouwmeester.core.authority import require_can_place
    from bouwmeester.core.permissions import build_permission_context

    member_ctx = await build_permission_context(tree.db, tree.member)
    with pytest.raises(HTTPException):
        await require_can_place(tree.db, member_ctx, None, tree.team)
    with pytest.raises(HTTPException):
        await require_can_place(tree.db, member_ctx, None, tree.team, ending=True)
    await require_can_place(tree.db, member_ctx, None, tree.team, contact=True)
    manager_ctx = await build_permission_context(tree.db, tree.directie_manager)
    await require_can_place(tree.db, manager_ctx, None, tree.team)
    anonymous = PermissionContext(is_authenticated=True)
    with pytest.raises(HTTPException) as refused:
        await require_can_place(tree.db, anonymous, None, tree.team, contact=True)
    assert refused.value.status_code == 403


async def test_member_links_contact_to_external_org(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert resp.status_code == 201, resp.text


async def test_member_links_contact_to_internal_eenheid(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.dg)
        )
    assert resp.status_code == 201, resp.text


async def test_member_cannot_link_account_to_external_org(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Placement requests
# ---------------------------------------------------------------------------


async def _request(db: AsyncSession, person: Person, org: OrganisatieEenheid):
    req = OrgPlacementRequest(
        person_id=person.id, organisatie_eenheid_id=org.id, dienstverband="in_dienst"
    )
    db.add(req)
    await db.flush()
    return req


async def test_ancestor_manager_approves_request(tree: Tree):
    req = await _request(tree.db, tree.contact, tree.team)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 200, resp.text


async def test_manager_cannot_approve_own_request(tree: Tree):
    req = await _request(tree.db, tree.directie_manager, tree.team)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 403


async def test_member_cannot_approve_request(tree: Tree):
    req = await _request(tree.db, tree.contact, tree.team)
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Manager and structure of eenheden
# ---------------------------------------------------------------------------


async def test_editor_cannot_make_self_manager_of_parent(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.directie.id}",
            json={"manager_id": str(tree.editor.id)},
        )
    assert resp.status_code == 403
    roles = await tree.db.scalars(
        select(PersonRole.role_id).where(PersonRole.person_id == tree.editor.id)
    )
    assert "unit_manager" not in set(roles)


async def test_manager_cannot_name_manager_at_own_rank(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"manager_id": str(tree.member.id)},
        )
    assert resp.status_code == 403


async def test_editor_cannot_create_eenheid_with_manager(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            "/api/organisatie",
            json={
                "naam": "Nieuw team",
                "type": "team",
                "parent_id": str(tree.directie.id),
                "manager_id": str(tree.editor.id),
            },
        )
    assert resp.status_code == 403


async def test_ministry_admin_names_manager_below(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"manager_id": str(tree.editor.id)},
        )
    assert resp.status_code == 200, resp.text


async def test_editor_cannot_move_team_under_other_parent(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"parent_id": str(tree.ministerie.id)},
        )
    assert resp.status_code == 403


async def test_editor_cannot_detach_team_as_external(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"type": "gemeente", "parent_id": None},
        )
    assert resp.status_code == 403


async def test_manager_cannot_pull_foreign_eenheid_under_own(tree: Tree):
    """Managing the new parent is not enough: you must manage the eenheid too."""
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.dg.id}",
            json={"parent_id": str(tree.directie.id)},
        )
    assert resp.status_code in (400, 403)
    other = await make_org(tree.db, "Andere directie", "directie", tree.ministerie)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.put(
            f"/api/organisatie/{other.id}",
            json={"parent_id": str(tree.directie.id)},
        )
    assert resp.status_code == 403


async def test_manager_moves_team_within_own_subtree(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"parent_id": str(tree.sibling.id)},
        )
    assert resp.status_code == 200, resp.text


async def test_dienst_counts_as_internal(tree: Tree):
    dienst = await make_org(tree.db, "Dienst", "dienst", tree.dg)
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{dienst.id}",
            json={"parent_id": str(tree.gemeente.id)},
        )
    assert resp.status_code == 403


async def test_renaming_needs_rights_on_the_eenheid_not_visibility(tree: Tree):
    """Unchanged structural fields do not trip the guards; seeing is not editing."""
    body = {
        "naam": "Team met nieuwe naam",
        "parent_id": str(tree.directie.id),
        "manager_id": None,
    }
    async with client_as(tree.db, tree.editor) as c:
        editor = await c.put(f"/api/organisatie/{tree.team.id}", json=body)
    async with client_as(tree.db, tree.directie_manager) as c:
        manager = await c.put(f"/api/organisatie/{tree.team.id}", json=body)
    assert editor.status_code == 403
    assert manager.status_code == 200, manager.text


async def test_two_active_managers_do_not_break_edits(tree: Tree):
    await grant_role(tree.db, tree.member, "unit_manager", tree.sibling)
    await grant_role(tree.db, tree.editor, "unit_manager", tree.sibling)
    async with client_as(tree.db, tree.super_admin) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.sibling.id}", json={"naam": "Hernoemd"}
        )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def _assign(person: Person, role: str, org: OrganisatieEenheid | None) -> dict:
    return {
        "person_id": str(person.id),
        "role_id": role,
        "organisatie_eenheid_id": str(org.id) if org else None,
    }


async def test_cannot_assign_role_to_self(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.post(
            "/api/roles/assign", json=_assign(tree.ministry_admin, "editor", tree.team)
        )
    assert resp.status_code == 403


async def test_ministry_admin_cannot_assign_above_own_scope(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.post(
            "/api/roles/assign",
            json=_assign(tree.member, "editor", tree.ministerie),
        )
    assert resp.status_code == 403


async def test_ministry_admin_assigns_within_subtree(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.post(
            "/api/roles/assign", json=_assign(tree.member, "editor", tree.team)
        )
    assert resp.status_code == 200, resp.text


async def test_platform_admin_cannot_assign_system_role(tree: Tree):
    async with client_as(tree.db, tree.platform_admin) as c:
        resp = await c.post(
            "/api/roles/assign", json=_assign(tree.member, "platform_admin", None)
        )
    assert resp.status_code == 403


async def test_platform_admin_cannot_grant_super_admin(tree: Tree):
    async with client_as(tree.db, tree.platform_admin) as c:
        resp = await c.patch(
            f"/api/admin/users/{tree.platform_admin.id}", json={"is_admin": True}
        )
    assert resp.status_code == 403


async def test_admin_user_refuses_non_admin():
    person = SimpleNamespace(id=uuid.uuid4())
    ctx = PermissionContext(person_id=person.id, is_authenticated=True)
    with pytest.raises(HTTPException) as exc:
        await get_admin_user(person, ctx)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Person records and emails
# ---------------------------------------------------------------------------


async def test_member_cannot_edit_colleague_email(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.editor.id}/emails",
            json={"email": "overname@example.com"},
        )
    assert resp.status_code == 403


async def test_member_cannot_rename_colleague(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.put(f"/api/people/{tree.editor.id}", json={"naam": "X"})
    assert resp.status_code == 403


async def test_member_edits_own_record(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.put(f"/api/people/{tree.member.id}", json={"functie": "Nieuw"})
    assert resp.status_code == 200, resp.text


async def test_member_edits_contact(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/phones",
            json={"phone_number": "0612345678", "label": "werk"},
        )
    assert resp.status_code == 201, resp.text


async def test_manager_edits_team_member_profile_not_email(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        profile = await c.put(
            f"/api/people/{tree.member.id}", json={"functie": "Beleidsmedewerker"}
        )
        email = await c.post(
            f"/api/people/{tree.member.id}/emails",
            json={"email": "ander-adres@example.com"},
        )
    assert profile.status_code == 200, profile.text
    assert email.status_code == 403


async def test_ministry_admin_cannot_move_admin_email(tree: Tree):
    """Emails decide who the admin seed promotes: never editable by others."""
    email_id = await tree.db.scalar(
        select(PersonEmail.id).where(PersonEmail.person_id == tree.super_admin.id)
    )
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.delete(f"/api/people/{tree.super_admin.id}/emails/{email_id}")
    assert resp.status_code == 403


async def test_email_case_variant_is_the_same_address(tree: Tree):
    taken = (await _email_of(tree.db, tree.super_admin)).upper()
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post("/api/people", json={"naam": "Stroman", "email": taken})
    assert resp.status_code == 409


async def test_ministry_admin_cannot_delete_account(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.delete(f"/api/people/{tree.platform_admin.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Resource roles
# ---------------------------------------------------------------------------


async def _initiatief(db: AsyncSession) -> Initiatief:
    initiatief = Initiatief(id=uuid.uuid4(), naam=f"Init {uuid.uuid4().hex[:6]}")
    db.add(initiatief)
    await db.flush()
    return initiatief


async def _node(db: AsyncSession) -> CorpusNode:
    node = CorpusNode(id=uuid.uuid4(), title="N", node_type="dossier", status="actief")
    db.add(node)
    await db.flush()
    return node


async def test_only_owner_grants_on_unlinked_initiatief(tree: Tree):
    initiatief = await _initiatief(tree.db)
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/resource-permissions/initiatief/{initiatief.id}",
            json={"person_id": str(tree.member.id), "rol": "viewer"},
        )
    # the initiatief is not visible to them: refused as if missing
    assert resp.status_code == 404


async def _link_initiatief(
    db: AsyncSession, initiatief: Initiatief, org: OrganisatieEenheid, rol: str
) -> None:
    db.add(
        ResourcePermission(
            organisatie_eenheid_id=org.id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol=rol,
        )
    )
    await db.flush()


async def test_read_link_gives_no_authority_over_initiatief(tree: Tree):
    initiatief = await _initiatief(tree.db)
    await _link_initiatief(tree.db, initiatief, tree.team, "viewer")
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/resource-permissions/initiatief/{initiatief.id}",
            json={"person_id": str(tree.member.id), "rol": "eigenaar"},
        )
    assert resp.status_code == 403


async def test_owning_eenheid_editor_grants_on_initiatief(tree: Tree):
    initiatief = await _initiatief(tree.db)
    await _link_initiatief(tree.db, initiatief, tree.team, "eigenaar")
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/resource-permissions/initiatief/{initiatief.id}",
            json={"person_id": str(tree.member.id), "rol": "contributor"},
        )
    assert resp.status_code == 200, resp.text


async def test_last_owner_cannot_leave(tree: Tree):
    initiatief = await _initiatief(tree.db)
    grant = ResourcePermission(
        person_id=tree.member.id,
        resource_type="initiatief",
        resource_id=initiatief.id,
        rol="eigenaar",
    )
    tree.db.add(grant)
    await tree.db.flush()
    async with client_as(tree.db, tree.member) as c:
        resp = await c.delete(f"/api/resource-permissions/{grant.id}")
    assert resp.status_code == 409


async def test_reader_without_authority_does_not_learn_the_last_owner(tree: Tree):
    """Authority comes first: a mere reader gets 403, not "last eigenaar"."""
    initiatief = await _initiatief(tree.db)
    owner = ResourcePermission(
        person_id=tree.member.id,
        resource_type="initiatief",
        resource_id=initiatief.id,
        rol="eigenaar",
    )
    tree.db.add_all(
        [
            owner,
            ResourcePermission(
                person_id=tree.editor.id,
                resource_type="initiatief",
                resource_id=initiatief.id,
                rol="viewer",
            ),
        ]
    )
    await tree.db.flush()
    async with client_as(tree.db, tree.editor) as c:
        seen = await c.get(f"/api/initiatieven/{initiatief.id}")
        removed = await c.delete(f"/api/resource-permissions/{owner.id}")
    assert seen.status_code == 200, seen.text
    assert removed.status_code == 403, removed.text
    async with client_as(tree.db, tree.member) as c:
        own = await c.delete(f"/api/resource-permissions/{owner.id}")
    assert own.status_code == 409, own.text


async def test_owner_hands_out_roles(tree: Tree):
    initiatief = await _initiatief(tree.db)
    tree.db.add(
        ResourcePermission(
            person_id=tree.member.id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol="eigenaar",
        )
    )
    await tree.db.flush()
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/resource-permissions/initiatief/{initiatief.id}",
            json={"person_id": str(tree.editor.id), "rol": "contributor"},
        )
    assert resp.status_code == 200, resp.text


async def test_editor_adds_self_as_node_stakeholder(tree: Tree):
    node = await _node(tree.db)
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/nodes/{node.id}/stakeholders",
            json={"person_id": str(tree.editor.id), "rol": "betrokken"},
        )
    assert resp.status_code == 201, resp.text


async def test_editor_adds_node_stakeholder_but_not_owner(tree: Tree):
    node = await _node(tree.db)
    async with client_as(tree.db, tree.editor) as c:
        betrokken = await c.post(
            f"/api/nodes/{node.id}/stakeholders",
            json={"person_id": str(tree.member.id), "rol": "betrokken"},
        )
        eigenaar = await c.post(
            f"/api/nodes/{node.id}/stakeholders",
            json={"person_id": str(tree.contact.id), "rol": "eigenaar"},
        )
    assert betrokken.status_code == 201, betrokken.text
    assert eigenaar.status_code == 403


async def test_editor_cannot_make_colleague_initiatief_eigenaar(tree: Tree):
    """eigenaar gives initiatief:delete, which an editor above the team lacks.

    resource_permission:manage used to be enough: two such editors could
    make each other eigenaar and then delete the initiatief.
    """
    initiatief = await _initiatief(tree.db)
    await _link_initiatief(tree.db, initiatief, tree.team, "eigenaar")
    directie_editor = await make_person(tree.db, "Directieredacteur")
    await place(tree.db, directie_editor, tree.directie)
    await grant_role(tree.db, directie_editor, "editor", tree.directie)
    url = f"/api/resource-permissions/initiatief/{initiatief.id}"
    async with client_as(tree.db, directie_editor) as c:
        owner = await c.post(
            url, json={"person_id": str(tree.contact.id), "rol": "eigenaar"}
        )
        contributor = await c.post(
            url, json={"person_id": str(tree.contact.id), "rol": "contributor"}
        )
    assert owner.status_code == 403
    assert contributor.status_code == 200, contributor.text


async def test_manager_makes_colleague_initiatief_eigenaar(tree: Tree):
    initiatief = await _initiatief(tree.db)
    await _link_initiatief(tree.db, initiatief, tree.team, "eigenaar")
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/resource-permissions/initiatief/{initiatief.id}",
            json={"person_id": str(tree.member.id), "rol": "eigenaar"},
        )
    assert resp.status_code == 200, resp.text


async def test_grants_are_listed_only_where_you_may_grant(tree: Tree):
    """resource_permission:manage somewhere else no longer lists the grants."""
    initiatief = await _initiatief(tree.db)
    await _link_initiatief(tree.db, initiatief, tree.team, "eigenaar")
    elsewhere = await make_person(tree.db, "Redacteur elders")
    await place(tree.db, elsewhere, tree.sibling)
    await grant_role(tree.db, elsewhere, "editor", tree.sibling)
    url = f"/api/resource-permissions/initiatief/{initiatief.id}"
    async with client_as(tree.db, elsewhere) as c:
        refused = await c.get(url)
    async with client_as(tree.db, tree.editor) as c:
        allowed = await c.get(url)
    assert refused.status_code == 404  # not visible to them either
    assert allowed.status_code == 200, allowed.text


async def test_member_leaves_node_without_any_rights(tree: Tree):
    """Leaving is always possible, whatever you may do on the node."""
    node = await _node(tree.db)
    grant = ResourcePermission(
        person_id=tree.member.id,
        resource_type="corpus_node",
        resource_id=node.id,
        rol="adviseur",
    )
    tree.db.add(grant)
    await tree.db.flush()
    async with client_as(tree.db, tree.member) as c:
        resp = await c.delete(f"/api/resource-permissions/{grant.id}")
    assert resp.status_code == 200, resp.text


async def test_owner_steps_down_but_cannot_step_up(tree: Tree):
    initiatief = await _initiatief(tree.db)
    grants = [
        ResourcePermission(
            person_id=person.id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol=rol,
        )
        for person, rol in (
            (tree.member, "eigenaar"),
            (tree.editor, "viewer"),
            (tree.directie_manager, "eigenaar"),
        )
    ]
    tree.db.add_all(grants)
    await tree.db.flush()
    async with client_as(tree.db, tree.editor) as c:
        up = await c.put(
            f"/api/resource-permissions/{grants[1].id}", json={"rol": "eigenaar"}
        )
    async with client_as(tree.db, tree.member) as c:
        down = await c.put(
            f"/api/resource-permissions/{grants[0].id}", json={"rol": "viewer"}
        )
    assert up.status_code == 403
    assert down.status_code == 200, down.text


# ---------------------------------------------------------------------------
# Tenant-wide admin actions
# ---------------------------------------------------------------------------


async def test_scoped_ministry_admin_cannot_merge_eenheden(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.post(
            "/api/admin/reconciliation/manual-merge",
            json={"source_id": str(tree.team.id), "target_id": str(tree.sibling.id)},
        )
    assert resp.status_code == 403


async def test_scoped_ministry_admin_cannot_trigger_sync(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        resp = await c.post("/api/admin/sync/tooi")
    assert resp.status_code == 403


async def test_module_toggle_only_within_own_subtree(tree: Tree):
    async with client_as(tree.db, tree.ministry_admin) as c:
        inside = await c.get(f"/api/eenheid-modules/{tree.team.id}")
        outside = await c.get(f"/api/eenheid-modules/{tree.gemeente.id}")
    assert inside.status_code == 200, inside.text
    assert outside.status_code == 403


async def test_member_cannot_create_edge_type(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            "/api/edge-types", json={"id": "x_test", "label_nl": "X", "label_en": "X"}
        )
    assert resp.status_code == 403


async def test_member_creates_initiatief_and_owns_it(tree: Tree):
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post("/api/initiatieven", json={"naam": "Eigen initiatief"})
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Chat write tools
# ---------------------------------------------------------------------------


async def test_chat_add_stakeholder_needs_permission(tree: Tree):
    from bouwmeester.services.chat_service import _execute_write_tool

    node = await _node(tree.db)
    result = await _execute_write_tool(
        "add_stakeholder",
        {"node_id": str(node.id), "person_id": str(tree.member.id), "rol": "eigenaar"},
        tree.db,
        person_id=tree.member.id,
    )
    assert result["success"] is False
    granted = await tree.db.scalar(
        select(ResourcePermission).where(ResourcePermission.resource_id == node.id)
    )
    assert granted is None


async def test_chat_editor_cannot_name_node_owner(tree: Tree):
    from bouwmeester.services.chat_service import _execute_write_tool

    node = await _node(tree.db)
    result = await _execute_write_tool(
        "add_stakeholder",
        {"node_id": str(node.id), "person_id": str(tree.member.id), "rol": "eigenaar"},
        tree.db,
        person_id=tree.editor.id,
    )
    assert result["success"] is False


async def test_chat_add_stakeholder_rejects_unknown_rol(tree: Tree):
    from bouwmeester.services.chat_service import _execute_write_tool

    node = await _node(tree.db)
    result = await _execute_write_tool(
        "add_stakeholder",
        {"node_id": str(node.id), "person_id": str(tree.member.id), "rol": "baas"},
        tree.db,
        person_id=tree.editor.id,
    )
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Identity: linking logins to persons
# ---------------------------------------------------------------------------


async def test_unverified_email_does_not_take_over_person(tree: Tree):
    email = await _email_of(tree.db, tree.contact)
    person = await get_or_create_person(
        tree.db, sub="attacker-sub", email=email, name="A", email_verified=False
    )
    assert person.id != tree.contact.id


async def test_verified_email_does_not_rebind_other_subject(tree: Tree):
    email = await _email_of(tree.db, tree.member)
    person = await get_or_create_person(
        tree.db, sub="second-idp-account", email=email, name="B", email_verified=True
    )
    assert person.id != tree.member.id
    await tree.db.refresh(tree.member)
    assert tree.member.oidc_subject != "second-idp-account"


async def test_verified_email_links_unbound_person(tree: Tree):
    email = await _email_of(tree.db, tree.contact)
    person = await get_or_create_person(
        tree.db, sub="contact-sub", email=email.upper(), name="C", email_verified=True
    )
    assert person.id == tree.contact.id
    assert person.oidc_email == email


async def test_admin_seed_ignores_legacy_email_column(tree: Tree):
    from bouwmeester.core import whitelist

    admin_email = f"seed-admin-{uuid.uuid4().hex[:8]}@example.com"
    # The free-text legacy column happens to hold a seeded admin address.
    tree.member.email = admin_email
    await tree.db.flush()

    with patch.object(whitelist, "_load_emails_from_file", return_value={admin_email}):
        await whitelist.seed_admins_from_file(tree.db)

    roles = await tree.db.scalars(
        select(PersonRole.role_id).where(PersonRole.person_id == tree.member.id)
    )
    assert "super_admin" not in set(roles)


# ---------------------------------------------------------------------------
# Fail-closed authentication
# ---------------------------------------------------------------------------


def _fake_request(path: str) -> SimpleNamespace:
    return SimpleNamespace(url=SimpleNamespace(path=path))


async def test_optional_user_fails_closed_on_private_route():
    settings = SimpleNamespace(OIDC_ISSUER="https://idp.example")
    with patch("bouwmeester.core.auth._resolve_user", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await get_optional_user(_fake_request("/api/people"), None, settings)
        public = await get_optional_user(
            _fake_request("/api/public/initiatieven/by-slug/x"), None, settings
        )
    assert exc.value.status_code == 401
    assert public is None


def test_only_the_login_flow_is_public():
    assert is_public_path("/api/auth/status")
    assert is_public_path("/api/auth/callback")
    assert not is_public_path("/api/auth/me")
    assert not is_public_path("/api/auth/onboarding")


async def test_bearer_token_needs_whitelisted_email():
    settings = SimpleNamespace(OIDC_ISSUER="https://idp.example")
    with (
        patch("bouwmeester.core.auth.get_jwks", AsyncMock(return_value={"keys": []})),
        patch(
            "bouwmeester.core.auth.validate_jwt_locally",
            return_value={"sub": "svc", "azp": "bouwmeester"},
        ),
        patch("bouwmeester.core.whitelist.is_email_allowed", return_value=False),
    ):
        assert await validate_bearer_token("t", settings) is None


# ---------------------------------------------------------------------------
# Round-two scenarios
# ---------------------------------------------------------------------------


async def test_editor_cannot_make_self_opdracht_owner(tree: Tree):
    from bouwmeester.models.opdracht import Opdracht

    opdracht = Opdracht(
        id=uuid.uuid4(),
        type="opdracht",
        titel="Onderzoek",
        begrotingsjaar=2026,
        opdrachtgever_id=tree.team.id,
    )
    tree.db.add(opdracht)
    await tree.db.flush()
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/opdrachten/{opdracht.id}/members",
            json={"person_id": str(tree.editor.id), "rol": "eigenaar"},
        )
        other = await c.post(
            f"/api/opdrachten/{opdracht.id}/members",
            json={"person_id": str(tree.member.id), "rol": "betrokken"},
        )
    assert resp.status_code == 403
    assert other.status_code == 201, other.text


async def test_editor_cannot_make_own_team_opdracht_owner(tree: Tree):
    """A grant to your own eenheid reaches you, so it counts as a self-grant."""
    from bouwmeester.models.opdracht import Opdracht

    opdracht = Opdracht(
        id=uuid.uuid4(),
        type="opdracht",
        titel="Onderzoek",
        begrotingsjaar=2026,
        opdrachtgever_id=tree.team.id,
    )
    tree.db.add(opdracht)
    await tree.db.flush()
    async with client_as(tree.db, tree.editor) as c:
        own_team = await c.post(
            f"/api/opdrachten/{opdracht.id}/eenheden",
            json={"eenheid_id": str(tree.team.id), "rol": "eigenaar"},
        )
        other_team = await c.post(
            f"/api/opdrachten/{opdracht.id}/eenheden",
            json={"eenheid_id": str(tree.sibling.id), "rol": "betrokken"},
        )
    assert own_team.status_code == 403
    assert other_team.status_code == 201, other_team.text


def test_ai_matches_grant_nothing():
    from bouwmeester.core.resource_roles import RESOURCE_ROLE_PERMISSIONS
    from bouwmeester.services.opdracht_matching_service import AI_GRANTED_ROL

    assert RESOURCE_ROLE_PERMISSIONS["opdracht"][AI_GRANTED_ROL] == set()


async def test_platform_admin_does_not_staff_the_organisation(tree: Tree):
    async with client_as(tree.db, tree.platform_admin) as c:
        resp = await c.post(
            "/api/roles/assign",
            json=_assign(tree.member, "ministry_admin", tree.dg),
        )
    assert resp.status_code == 403


async def test_ministry_admin_revokes_within_subtree_only(tree: Tree):
    inside = await grant_role(tree.db, tree.member, "editor", tree.sibling)
    outside = await grant_role(tree.db, tree.member, "editor", tree.ministerie)
    async with client_as(tree.db, tree.ministry_admin) as c:
        ok = await c.delete(f"/api/roles/assignments/{inside.id}")
        refused = await c.delete(f"/api/roles/assignments/{outside.id}")
    assert ok.status_code == 200, ok.text
    assert refused.status_code == 403


async def test_super_admin_cannot_revoke_own_super_admin(tree: Tree):
    assignment = await tree.db.scalar(
        select(PersonRole).where(
            PersonRole.person_id == tree.super_admin.id,
            PersonRole.role_id == "super_admin",
        )
    )
    async with client_as(tree.db, tree.super_admin) as c:
        resp = await c.delete(f"/api/roles/assignments/{assignment.id}")
    assert resp.status_code == 400, resp.text
    assert "eigen" in resp.json()["detail"].lower()


async def test_editor_cannot_dissolve_team(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"geldig_tot": str(date.today())},
        )
    assert resp.status_code == 403


async def test_external_eenheid_with_internal_part_is_not_free_to_move(tree: Tree):
    zbo = await make_org(tree.db, "Zbo", "zbo")
    await make_org(tree.db, "Intern team", "team", zbo)
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{zbo.id}", json={"parent_id": str(tree.gemeente.id)}
        )
    assert resp.status_code == 403


async def test_sharing_needs_authority_over_the_source(tree: Tree):
    """The route and ``eenheid:share`` decide alike."""
    from tests.authz_world import ask

    share = {"target_eenheid_id": str(tree.gemeente.id), "access_level": "read"}
    sources = [tree.team, tree.ministerie]
    async with client_as(tree.db, tree.ministry_admin) as c:
        asked = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask(
                        "eenheid:share",
                        "organisatie_eenheid",
                        source.id,
                        target_eenheid_id=tree.gemeente.id,
                    )
                    for source in sources
                ]
            },
        )
        inside, outside = [
            await c.post(
                "/api/sharing", json={**share, "source_eenheid_id": str(source.id)}
            )
            for source in sources
        ]
    assert [d["decision"] for d in asked.json()["evaluations"]] == [True, False]
    assert inside.status_code == 200, inside.text
    assert outside.status_code == 403


async def test_sharing_with_own_eenheid_is_refused_alike(tree: Tree):
    from tests.authz_world import ask

    async with client_as(tree.db, tree.ministry_admin) as c:
        asked = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask(
                        "eenheid:share",
                        "organisatie_eenheid",
                        tree.team.id,
                        target_eenheid_id=tree.dg.id,
                    )
                ]
            },
        )
        shared = await c.post(
            "/api/sharing",
            json={
                "source_eenheid_id": str(tree.team.id),
                "target_eenheid_id": str(tree.dg.id),
                "access_level": "read",
            },
        )
    assert asked.json()["evaluations"][0]["decision"] is False
    assert shared.status_code == 403, shared.text


async def test_pending_requests_follow_the_managed_subtree(tree: Tree):
    in_tree = await _request(tree.db, tree.contact, tree.team)
    above = await _request(tree.db, tree.contact, tree.dg)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.get("/api/org-placements/pending")
    ids = {r["id"] for r in resp.json()}
    assert str(in_tree.id) in ids
    assert str(above.id) not in ids


async def test_manager_sees_managed_subtree(tree: Tree):
    from bouwmeester.core.org_context import build_org_context

    ctx = await build_org_context(tree.db, tree.directie_manager)
    assert {tree.directie.id, tree.team.id, tree.sibling.id} <= set(
        ctx.visible_eenheid_ids
    )


async def _first_login(tree: Tree, person: Person) -> Person:
    email = await _email_of(tree.db, person)
    return await get_or_create_person(
        tree.db,
        sub=f"login-{uuid.uuid4().hex}",
        email=email,
        name="",
        email_verified=True,
    )


async def _pending_requests(tree: Tree, person: Person) -> set[uuid.UUID]:
    rows = await tree.db.scalars(
        select(OrgPlacementRequest.organisatie_eenheid_id).where(
            OrgPlacementRequest.person_id == person.id,
            OrgPlacementRequest.status == "pending",
        )
    )
    return set(rows)


async def test_first_login_keeps_placements(tree: Tree):
    """A manager who placed a new hire before their first login keeps it."""
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.team)
        )
    assert resp.status_code == 201, resp.text

    person = await _first_login(tree, tree.contact)

    assert person.id == tree.contact.id
    assert await _placement_of(tree.db, tree.contact, tree.team) is not None
    assert await _pending_requests(tree, tree.contact) == set()


async def test_contact_placement_waits_for_a_manager_at_first_login(tree: Tree):
    """A member may place a contact, but that grants no access on login."""
    async with client_as(tree.db, tree.member) as c:
        internal = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.team)
        )
        external = await c.post(
            f"/api/people/{tree.contact.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert internal.status_code == 201, internal.text
    assert external.status_code == 201, external.text

    await _first_login(tree, tree.contact)

    assert await _placement_of(tree.db, tree.contact, tree.team) is None
    assert await _pending_requests(tree, tree.contact) == {tree.team.id}
    assert await _placement_of(tree.db, tree.contact, tree.gemeente) is not None
    notified = await tree.db.scalar(
        select(Notification.id).where(
            Notification.person_id == tree.directie_manager.id,
            Notification.type == "placement_request",
        )
    )
    assert notified is not None


def _migration(name: str):
    import importlib.util
    from pathlib import Path

    import bouwmeester.migrations

    versions = Path(bouwmeester.migrations.__file__).parent / "versions"
    spec = importlib.util.spec_from_file_location(name, versions / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_migration_confirms_placements_made_before_deploy(tree: Tree):
    """A manager's placement from before the fix survives the first login."""
    from sqlalchemy import text

    below_team = await make_org(tree.db, "Stichting", "stichting", tree.team)
    ended = await make_person(tree.db, "Vertrokken", account=False)
    for person, org in (
        (tree.contact, tree.team),
        (tree.contact, below_team),
        (tree.contact, tree.gemeente),
        (ended, tree.team),
    ):
        await place(tree.db, person, org, bron="handmatig")
    # A week back, not yesterday: the migration compares with the database's
    # CURRENT_DATE (UTC), which trails local midnight by a day for two hours.
    (await _placement_of(tree.db, ended, tree.team)).eind_datum = (
        date.today() - timedelta(days=7)
    )
    await tree.db.flush()

    migration = _migration("7c1e5a9d3b20_confirm_existing_placements")
    await tree.db.execute(text(migration.CONFIRM_SQL))

    async def bron(person: Person, org: OrganisatieEenheid) -> str:
        return await tree.db.scalar(
            select(PersonOrganisatieEenheid.bron).where(
                PersonOrganisatieEenheid.person_id == person.id,
                PersonOrganisatieEenheid.organisatie_eenheid_id == org.id,
            )
        )

    assert await bron(tree.contact, tree.team) == "leidinggevende"
    assert await bron(tree.contact, below_team) == "leidinggevende"
    assert await bron(tree.contact, tree.gemeente) == "handmatig"
    assert await bron(ended, tree.team) == "handmatig"

    await _first_login(tree, tree.contact)
    assert await _placement_of(tree.db, tree.contact, tree.team) is not None
    assert await _pending_requests(tree, tree.contact) == set()


async def test_reopened_contact_placement_is_no_longer_confirmed(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.team)
        )
    placement_id = resp.json()["id"]
    async with client_as(tree.db, tree.member) as c:
        resp = await c.put(
            f"/api/people/{tree.contact.id}/organisaties/{placement_id}",
            json={"dienstverband": "ingehuurd"},
        )
    assert resp.status_code == 200, resp.text

    await _first_login(tree, tree.contact)

    assert await _pending_requests(tree, tree.contact) == {tree.team.id}


async def _opdracht(db: AsyncSession, **eenheden) -> Opdracht:
    opdracht = Opdracht(
        id=uuid.uuid4(),
        type="opdracht",
        titel="Onderzoek",
        begrotingsjaar=2026,
        **eenheden,
    )
    db.add(opdracht)
    await db.flush()
    return opdracht


async def test_contacts_on_opdracht_without_eenheid(tree: Tree):
    """FCC imports leave the eenheden empty; contacts stay manageable."""
    opdracht = await _opdracht(tree.db)
    async with client_as(tree.db, tree.editor) as c:
        contact = await c.post(
            f"/api/opdrachten/{opdracht.id}/members",
            json={"person_id": str(tree.member.id), "rol": "contactpersoon"},
        )
        owner = await c.post(
            f"/api/opdrachten/{opdracht.id}/members",
            json={"person_id": str(tree.member.id), "rol": "eigenaar"},
        )
    assert contact.status_code == 201, contact.text
    assert owner.status_code == 403


async def test_opdrachtnemer_team_answers_for_opdracht(tree: Tree):
    opdracht = await _opdracht(tree.db, opdrachtnemer_eenheid_id=tree.team.id)
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.post(
            f"/api/opdrachten/{opdracht.id}/members",
            json={"person_id": str(tree.member.id), "rol": "betrokken"},
        )
    assert resp.status_code == 201, resp.text


async def test_initiatief_member_route_uses_the_same_rules(tree: Tree):
    """A manager elsewhere is no eigenaar of every initiatief any more."""
    initiatief = await _initiatief(tree.db)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/initiatieven/{initiatief.id}/members",
            json={"person_id": str(tree.directie_manager.id), "rol": "eigenaar"},
        )
    # the initiatief is not visible to them: refused as if missing
    assert resp.status_code == 404


async def test_manager_links_own_staff_to_external_org(tree: Tree):
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert resp.status_code == 201, resp.text


async def test_ending_someone_elses_placement_says_so(tree: Tree):
    placement = await _placement_of(tree.db, tree.editor, tree.team)
    async with client_as(tree.db, tree.member) as c:
        resp = await c.put(
            f"/api/people/{tree.editor.id}/organisaties/{placement.id}",
            json={"eind_datum": str(date.today())},
        )
    assert resp.status_code == 403
    assert "beëindigen" in resp.json()["detail"]


async def test_every_manager_above_hears_of_a_request(tree: Tree):
    from bouwmeester.models.notification import Notification
    from bouwmeester.services.notification_service import NotificationService

    await NotificationService(tree.db).notify_placement_request(
        person_naam="Nieuw", eenheid_id=tree.team.id, eenheid_naam="Team"
    )
    notified = set(
        await tree.db.scalars(
            select(Notification.person_id).where(
                Notification.type == "placement_request"
            )
        )
    )
    assert {tree.directie_manager.id, tree.ministry_admin.id} <= notified
    assert tree.editor.id not in notified


async def test_own_request_is_not_in_own_approval_list(tree: Tree):
    own = await _request(tree.db, tree.directie_manager, tree.team)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.get("/api/org-placements/pending")
    assert str(own.id) not in {r["id"] for r in resp.json()}


async def test_approving_an_existing_placement_conflicts(tree: Tree):
    req = await _request(tree.db, tree.member, tree.team)
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 409


async def test_admin_seed_skips_address_added_to_own_profile(tree: Tree):
    from bouwmeester.core import whitelist

    admin_email = f"future-admin-{uuid.uuid4().hex[:8]}@example.com"
    tree.db.add(PersonEmail(person_id=tree.member.id, email=admin_email))
    await tree.db.flush()

    with patch.object(whitelist, "_load_emails_from_file", return_value={admin_email}):
        await whitelist.seed_admins_from_file(tree.db)

    roles = await tree.db.scalars(
        select(PersonRole.role_id).where(PersonRole.person_id == tree.member.id)
    )
    assert "super_admin" not in set(roles)


async def test_refusal_names_who_decides(tree: Tree):
    async with client_as(tree.db, tree.editor) as c:
        other = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
        self_ = await c.post(
            f"/api/people/{tree.editor.id}/organisaties", json=_placement(tree.sibling)
        )
    assert other.status_code == 403
    assert tree.directie_manager.naam in other.json()["detail"]
    assert tree.sibling.naam in other.json()["detail"]
    assert self_.status_code == 403
    assert "plaatsingsverzoek" in self_.json()["detail"]


async def _resolve_with_dev_cookie(tree: Tree, oidc_issuer: str):
    from bouwmeester.core.auth import DEV_PERSON_COOKIE, _resolve_user

    request = SimpleNamespace(cookies={DEV_PERSON_COOKIE: str(tree.editor.id)})
    settings = SimpleNamespace(OIDC_ISSUER=oidc_issuer)
    with (
        patch(
            "bouwmeester.core.auth._person_from_api_key", AsyncMock(return_value=None)
        ),
        patch(
            "bouwmeester.core.auth._person_from_webauthn_session",
            AsyncMock(return_value=None),
        ),
        patch("bouwmeester.core.auth._validate_token", AsyncMock(return_value=None)),
    ):
        return await _resolve_user(request, tree.db, settings)


async def test_dev_person_cookie_is_ignored_with_oidc(tree: Tree):
    """With an identity provider the dev picker's cookie means nothing."""
    assert await _resolve_with_dev_cookie(tree, "https://idp.example") is None


async def test_dev_person_cookie_acts_as_that_person_locally(tree: Tree):
    person = await _resolve_with_dev_cookie(tree, "")
    assert person is not None and person.id == tree.editor.id


# ---------------------------------------------------------------------------
# External eenheden inside the internal organisation
# ---------------------------------------------------------------------------


async def _other_ministry_dg(tree: Tree) -> OrganisatieEenheid:
    other = await make_org(tree.db, "Ander ministerie", "ministerie")
    return await make_org(tree.db, "Ander DG", "directoraat_generaal", other)


async def test_external_eenheid_cannot_smuggle_staff_into_another_ministry(
    tree: Tree,
):
    """A gemeente under another ministry's DG is inside the organisation.

    Creating it there needs org:create on that DG, and placing own staff in
    it is no detachering: its members would read that ministry up the line.
    """
    foreign_dg = await _other_ministry_dg(tree)
    body = {"naam": "Gemeente", "type": "gemeente", "parent_id": str(foreign_dg.id)}
    async with client_as(tree.db, tree.directie_manager) as c:
        created = await c.post("/api/organisatie", json=body)
    assert created.status_code == 403, created.text

    inside = await make_org(tree.db, "Gemeente binnen", "gemeente", foreign_dg)
    async with client_as(tree.db, tree.directie_manager) as c:
        placed = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(inside)
        )
    assert placed.status_code == 403, placed.text


async def test_external_eenheid_outside_the_organisation_stays_free(tree: Tree):
    """At the top or under another external eenheid, creating is free."""
    async with client_as(tree.db, tree.directie_manager) as c:
        top = await c.post(
            "/api/organisatie", json={"naam": "Stichting", "type": "stichting"}
        )
        below = await c.post(
            "/api/organisatie",
            json={
                "naam": "Wijkteam",
                "type": "gemeente",
                "parent_id": str(tree.gemeente.id),
            },
        )
        # A detachering: own staff in an external organisation.
        placed = await c.post(
            f"/api/people/{tree.member.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert top.status_code == 201, top.text
    assert below.status_code == 201, below.text
    assert placed.status_code == 201, placed.text


async def test_external_eenheid_moves_like_it_is_created(tree: Tree):
    """Moving into the organisation needs org:create on the new parent."""
    foreign_dg = await _other_ministry_dg(tree)
    async with client_as(tree.db, tree.directie_manager) as c:
        created = await c.post(
            "/api/organisatie", json={"naam": "Stichting", "type": "stichting"}
        )
        assert created.status_code == 201, created.text
        url = f"/api/organisatie/{created.json()['id']}"
        into_foreign = await c.put(url, json={"parent_id": str(foreign_dg.id)})
        under_external = await c.put(url, json={"parent_id": str(tree.gemeente.id)})
        into_own = await c.put(url, json={"parent_id": str(tree.directie.id)})
    assert into_foreign.status_code == 403, into_foreign.text
    assert under_external.status_code == 200, under_external.text
    assert into_own.status_code == 200, into_own.text


async def test_external_eenheid_leaves_the_organisation_only_with_rights_there(
    tree: Tree,
):
    inside = await make_org(tree.db, "Stichting", "stichting", tree.dg)
    tree.db.add(
        ResourcePermission(
            person_id=tree.editor.id,
            resource_type="organisatie_eenheid",
            resource_id=inside.id,
            rol="eigenaar",
        )
    )
    await tree.db.flush()
    async with client_as(tree.db, tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{inside.id}", json={"parent_id": str(tree.gemeente.id)}
        )
    assert resp.status_code == 403, resp.text


async def test_external_create_list_agrees_with_each_evaluation(tree: Tree):
    """``GET /authz/eenheden`` for a gemeente matches asking per parent."""
    from tests.authz_world import ask

    foreign_dg = await _other_ministry_dg(tree)
    parents = [tree.directie, tree.team, tree.dg, tree.gemeente, foreign_dg]
    async with client_as(tree.db, tree.directie_manager) as c:
        listed = (
            await c.get(
                "/api/authz/eenheden",
                params={"action": "org:create", "eenheid_type": "gemeente"},
            )
        ).json()
        evaluations = [
            ask(
                "org:create",
                "organisatie_eenheid",
                eenheid_type="gemeente",
                eenheid_id=p.id,
            )
            for p in parents
        ]
        decisions = (
            await c.post("/api/authz/evaluations", json={"evaluations": evaluations})
        ).json()["evaluations"]
    assert not listed["all"]
    got = {p.naam: str(p.id) in listed["ids"] for p in parents}
    assert got == {p.naam: d["decision"] for p, d in zip(parents, decisions)}
    assert got == {
        "Directie": True,
        "Team": True,
        "DG": False,
        "Gemeente": True,
        "Ander DG": False,
    }


# ---------------------------------------------------------------------------
# Only trusted placements give access
# ---------------------------------------------------------------------------


async def _visible_eenheden(tree: Tree, person: Person) -> set[uuid.UUID]:
    from bouwmeester.core.authz import perm_ctx_for, visibility

    org_ctx, _ = await visibility(tree.db, await perm_ctx_for(tree.db, person.id))
    return set(org_ctx.visible_eenheid_ids)


async def _may(tree: Tree, person: Person, action: str, initiatief_id) -> bool:
    from bouwmeester.core.authz import can, perm_ctx_for

    ctx = await perm_ctx_for(tree.db, person.id)
    return await can(tree.db, ctx, action, "initiatief", initiatief_id)


async def _initiatief_for(tree: Tree, eenheid: OrganisatieEenheid, rol: str):
    initiatief = Initiatief(id=uuid.uuid4(), naam=f"Init {uuid.uuid4().hex[:6]}")
    tree.db.add(initiatief)
    await tree.db.flush()
    tree.db.add(
        ResourcePermission(
            organisatie_eenheid_id=eenheid.id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol=rol,
        )
    )
    await tree.db.flush()
    return initiatief


async def test_contact_in_eenheid_moved_inside_does_not_read_up_the_line(tree: Tree):
    """A team editor cannot smuggle a contact into the organisation.

    Create a stichting at the top, place a contact there, let the contact
    log in, then hang the stichting under the own team: the contact's
    placement is contact administration and stays informational.
    """
    async with client_as(tree.db, tree.editor) as c:
        created = await c.post(
            "/api/organisatie", json={"naam": "Stichting", "type": "stichting"}
        )
        assert created.status_code == 201, created.text
        stichting = await tree.db.get(
            OrganisatieEenheid, uuid.UUID(created.json()["id"])
        )
        placed = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(stichting)
        )
        assert placed.status_code == 201, placed.text
    await _first_login(tree, tree.contact)
    async with client_as(tree.db, tree.editor) as c:
        moved = await c.put(
            f"/api/organisatie/{stichting.id}", json={"parent_id": str(tree.team.id)}
        )
    assert moved.status_code == 200, moved.text

    assert (await _placement_of(tree.db, tree.contact, stichting)).bron == "handmatig"
    visible = await _visible_eenheden(tree, tree.contact)
    assert not visible & {tree.team.id, tree.directie.id, tree.ministerie.id}


async def test_moving_trusted_members_inside_needs_a_manager_of_the_new_parent(
    tree: Tree,
):
    """Members of a moved eenheid read up the new line: a manager decides."""

    async def move_fractie_under_team(who: Person):
        async with client_as(tree.db, who) as c:
            created = await c.post(
                "/api/organisatie", json={"naam": "Fractie", "type": "stichting"}
            )
            assert created.status_code == 201, created.text
            fractie = await tree.db.get(
                OrganisatieEenheid, uuid.UUID(created.json()["id"])
            )
            kamerlid = await make_person(tree.db, "Kamerlid", account=False)
            await place(tree.db, kamerlid, fractie, bron="tk_odata")
            moved = await c.put(
                f"/api/organisatie/{fractie.id}", json={"parent_id": str(tree.team.id)}
            )
        return moved

    refused = await move_fractie_under_team(tree.editor)
    assert refused.status_code == 403, refused.text
    assert "bevestigde leden" in refused.json()["detail"]
    allowed = await move_fractie_under_team(tree.directie_manager)
    assert allowed.status_code == 200, allowed.text


async def test_detachering_gives_no_share_of_a_partner_grant(tree: Tree):
    """A manager detaching own staff to a partner records who works where."""
    initiatief = await _initiatief_for(tree, tree.gemeente, "contributor")
    async with client_as(tree.db, tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert resp.status_code == 201, resp.text
    placement = await _placement_of(tree.db, tree.member, tree.gemeente)
    assert placement.bron == "detachering"

    assert not await _may(tree, tree.member, "initiatief:read", initiatief.id)
    assert not await _may(tree, tree.member, "initiatief:update", initiatief.id)
    assert tree.gemeente.id not in await _visible_eenheden(tree, tree.member)


async def test_planted_contact_gets_no_share_of_a_partner_grant(tree: Tree):
    initiatief = await _initiatief_for(tree, tree.gemeente, "contributor")
    async with client_as(tree.db, tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert resp.status_code == 201, resp.text
    await _first_login(tree, tree.contact)

    assert not await _may(tree, tree.contact, "initiatief:read", initiatief.id)
    async with client_as(tree.db, tree.contact) as c:
        listed = await c.get("/api/initiatieven")
    assert listed.status_code == 200, listed.text
    assert str(initiatief.id) not in {i["id"] for i in listed.json()}


async def test_trusted_member_shares_the_partner_grant(tree: Tree):
    initiatief = await _initiatief_for(tree, tree.gemeente, "contributor")
    wethouder = await make_person(tree.db, "Wethouder")
    await place(tree.db, wethouder, tree.gemeente, bron="abd_scrape")

    assert await _may(tree, wethouder, "initiatief:read", initiatief.id)
    assert await _may(tree, wethouder, "initiatief:update", initiatief.id)


async def test_manager_confirms_a_contact_placement(tree: Tree):
    await place(tree.db, tree.contact, tree.team, bron="handmatig")
    async with client_as(tree.db, tree.member) as c:
        again = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.team)
        )
    assert again.status_code == 409, again.text
    async with client_as(tree.db, tree.directie_manager) as c:
        confirmed = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.team)
        )
        twice = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.team)
        )
    assert confirmed.status_code == 201, confirmed.text
    assert twice.status_code == 409, twice.text
    placement = await _placement_of(tree.db, tree.contact, tree.team)
    assert placement.bron == "leidinggevende"
