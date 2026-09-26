"""Who may change who has access to what.

Covers the grant-bearing actions guarded in ``core/authz.py``: placing
people in an eenheid, naming a manager, moving an eenheid, assigning roles,
deciding placement requests, editing someone's identity, promoting to
super_admin, tenant-wide admin actions, chat write tools, and linking a
login to an existing person.

Uses a realistic tree (ministerie > DG > directie > team, plus a sibling
team and an external gemeente) and real permission resolution: only the
current user is overridden, never the permission context.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import (
    get_admin_user,
    get_optional_user,
    get_or_create_person,
    validate_bearer_token,
)
from bouwmeester.core.database import get_db
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.org_naam import OrganisatieEenheidNaam
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _person(db: AsyncSession, naam: str, *, account: bool = True) -> Person:
    uid = uuid.uuid4()
    email = f"{naam.lower().replace(' ', '-')}-{uid.hex[:8]}@example.com"
    person = Person(
        id=uid,
        naam=naam,
        email=email,
        functie="tester",
        is_active=True,
        oidc_subject=f"sub-{uid.hex}" if account else None,
    )
    db.add(person)
    await db.flush()
    db.add(PersonEmail(person_id=person.id, email=email, is_default=True))
    await db.flush()
    return person


async def _org(
    db: AsyncSession, naam: str, type_: str, parent: OrganisatieEenheid | None = None
) -> OrganisatieEenheid:
    org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam=naam,
        type=type_,
        parent_id=parent.id if parent else None,
    )
    db.add(org)
    await db.flush()
    db.add(
        OrganisatieEenheidNaam(eenheid_id=org.id, naam=naam, geldig_van=date.today())
    )
    await db.flush()
    return org


async def _place(db: AsyncSession, person: Person, org: OrganisatieEenheid) -> None:
    db.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=org.id,
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db.flush()


async def _role(
    db: AsyncSession, person: Person, role_id: str, org: OrganisatieEenheid | None
) -> PersonRole:
    role = PersonRole(
        person_id=person.id,
        role_id=role_id,
        organisatie_eenheid_id=org.id if org else None,
        start_datum=date.today() - timedelta(days=1),
    )
    db.add(role)
    await db.flush()
    return role


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
    contact: Person  # external contact, no account
    db: AsyncSession


@pytest.fixture
async def tree(db_session: AsyncSession) -> Tree:
    db = db_session
    ministerie = await _org(db, "Ministerie", "ministerie")
    dg = await _org(db, "DG", "directoraat_generaal", ministerie)
    directie = await _org(db, "Directie", "directie", dg)
    team = await _org(db, "Team", "team", directie)
    sibling = await _org(db, "Ander team", "team", directie)
    gemeente = await _org(db, "Gemeente", "gemeente")

    member = await _person(db, "Lid")
    await _place(db, member, team)

    editor = await _person(db, "Redacteur")
    await _place(db, editor, team)
    await _role(db, editor, "editor", team)

    directie_manager = await _person(db, "Directeur")
    await _place(db, directie_manager, directie)
    await _role(db, directie_manager, "unit_manager", directie)

    ministry_admin = await _person(db, "DG-beheerder")
    await _place(db, ministry_admin, dg)
    await _role(db, ministry_admin, "ministry_admin", dg)

    platform_admin = await _person(db, "Platformbeheerder")
    await _role(db, platform_admin, "platform_admin", None)

    contact = await _person(db, "Contact", account=False)

    return Tree(
        ministerie,
        dg,
        directie,
        team,
        sibling,
        gemeente,
        member,
        editor,
        directie_manager,
        ministry_admin,
        platform_admin,
        contact,
        db,
    )


@pytest.fixture
async def as_user(tree: Tree):
    """Return a factory: ``async with as_user(person) as client``."""
    from contextlib import asynccontextmanager

    from bouwmeester.core.app import create_app

    @asynccontextmanager
    async def _client(person: Person):
        app = create_app()

        async def _db():
            yield tree.db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_optional_user] = lambda: person
        app.dependency_overrides[get_admin_user] = lambda: person
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer test"},
        ) as client:
            yield client

    return _client


def _placement(org: OrganisatieEenheid) -> dict:
    return {"organisatie_eenheid_id": str(org.id), "start_datum": str(date.today())}


# ---------------------------------------------------------------------------
# Placements
# ---------------------------------------------------------------------------


async def test_member_cannot_place_self_in_other_team(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
    assert resp.status_code == 403


async def test_editor_cannot_place_colleague_in_team(tree: Tree, as_user):
    async with as_user(tree.editor) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
    assert resp.status_code == 403


async def test_member_cannot_end_someone_elses_placement(tree: Tree, as_user):
    placement = await tree.db.scalar(
        select(PersonOrganisatieEenheid).where(
            PersonOrganisatieEenheid.person_id == tree.editor.id
        )
    )
    async with as_user(tree.member) as c:
        resp = await c.delete(
            f"/api/people/{tree.editor.id}/organisaties/{placement.id}"
        )
    assert resp.status_code == 403


async def test_manager_places_in_descendant_team(tree: Tree, as_user):
    async with as_user(tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.sibling)
        )
    assert resp.status_code == 201, resp.text


async def test_manager_cannot_place_outside_subtree(tree: Tree, as_user):
    async with as_user(tree.directie_manager) as c:
        resp = await c.post(
            f"/api/people/{tree.member.id}/organisaties", json=_placement(tree.dg)
        )
    assert resp.status_code == 403


async def test_member_links_contact_to_external_org(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties",
            json=_placement(tree.gemeente),
        )
    assert resp.status_code == 201, resp.text


async def test_member_links_contact_to_internal_eenheid(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/organisaties", json=_placement(tree.dg)
        )
    assert resp.status_code == 201, resp.text


async def test_member_cannot_link_account_to_external_org(tree: Tree, as_user):
    async with as_user(tree.member) as c:
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


async def test_ancestor_manager_approves_request(tree: Tree, as_user):
    req = await _request(tree.db, tree.contact, tree.team)
    async with as_user(tree.directie_manager) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 200, resp.text


async def test_manager_cannot_approve_own_request(tree: Tree, as_user):
    req = await _request(tree.db, tree.directie_manager, tree.team)
    async with as_user(tree.directie_manager) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 403


async def test_member_cannot_approve_request(tree: Tree, as_user):
    req = await _request(tree.db, tree.contact, tree.team)
    async with as_user(tree.member) as c:
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Manager and structure of eenheden
# ---------------------------------------------------------------------------


async def test_editor_cannot_make_self_manager_of_parent(tree: Tree, as_user):
    async with as_user(tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.directie.id}",
            json={"manager_id": str(tree.editor.id)},
        )
    assert resp.status_code == 403
    roles = await tree.db.scalars(
        select(PersonRole.role_id).where(PersonRole.person_id == tree.editor.id)
    )
    assert "unit_manager" not in set(roles)


async def test_editor_cannot_create_eenheid_with_manager(tree: Tree, as_user):
    async with as_user(tree.editor) as c:
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


async def test_ministry_admin_names_manager_below(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"manager_id": str(tree.editor.id)},
        )
    assert resp.status_code == 200, resp.text


async def test_editor_cannot_move_team_under_other_parent(tree: Tree, as_user):
    async with as_user(tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={"parent_id": str(tree.ministerie.id)},
        )
    assert resp.status_code == 403


async def test_editor_can_rename_visible_eenheid(tree: Tree, as_user):
    async with as_user(tree.editor) as c:
        resp = await c.put(
            f"/api/organisatie/{tree.team.id}",
            json={
                "naam": "Team met nieuwe naam",
                "parent_id": str(tree.directie.id),
                "manager_id": None,
            },
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


async def test_cannot_assign_role_to_self(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.post(
            "/api/roles/assign", json=_assign(tree.ministry_admin, "editor", tree.team)
        )
    assert resp.status_code == 403


async def test_ministry_admin_cannot_assign_above_own_scope(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.post(
            "/api/roles/assign",
            json=_assign(tree.member, "editor", tree.ministerie),
        )
    assert resp.status_code == 403


async def test_ministry_admin_assigns_within_subtree(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.post(
            "/api/roles/assign", json=_assign(tree.member, "editor", tree.team)
        )
    assert resp.status_code == 200, resp.text


async def test_platform_admin_cannot_assign_system_role(tree: Tree, as_user):
    async with as_user(tree.platform_admin) as c:
        resp = await c.post(
            "/api/roles/assign", json=_assign(tree.member, "platform_admin", None)
        )
    assert resp.status_code == 403


async def test_platform_admin_cannot_grant_super_admin(tree: Tree, as_user):
    async with as_user(tree.platform_admin) as c:
        resp = await c.patch(
            f"/api/admin/users/{tree.platform_admin.id}", json={"is_admin": True}
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Person records and emails
# ---------------------------------------------------------------------------


async def test_member_cannot_edit_colleague_email(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.editor.id}/emails",
            json={"email": "overname@example.com"},
        )
    assert resp.status_code == 403


async def test_member_cannot_rename_colleague(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.put(f"/api/people/{tree.editor.id}", json={"naam": "X"})
    assert resp.status_code == 403


async def test_member_edits_own_record(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.put(f"/api/people/{tree.member.id}", json={"functie": "Nieuw"})
    assert resp.status_code == 200, resp.text


async def test_member_edits_contact(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post(
            f"/api/people/{tree.contact.id}/phones",
            json={"phone_number": "0612345678", "label": "werk"},
        )
    assert resp.status_code == 201, resp.text


async def test_ministry_admin_cannot_delete_account(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.delete(f"/api/people/{tree.platform_admin.id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tenant-wide admin actions
# ---------------------------------------------------------------------------


async def test_scoped_ministry_admin_cannot_merge_eenheden(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.post(
            "/api/admin/reconciliation/manual-merge",
            json={"source_id": str(tree.team.id), "target_id": str(tree.sibling.id)},
        )
    assert resp.status_code == 403


async def test_scoped_ministry_admin_cannot_trigger_sync(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        resp = await c.post("/api/admin/sync/tooi")
    assert resp.status_code == 403


async def test_module_toggle_only_within_own_subtree(tree: Tree, as_user):
    async with as_user(tree.ministry_admin) as c:
        inside = await c.get(f"/api/eenheid-modules/{tree.team.id}")
        outside = await c.get(f"/api/eenheid-modules/{tree.gemeente.id}")
    assert inside.status_code == 200, inside.text
    assert outside.status_code == 403


async def test_member_cannot_create_edge_type(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post(
            "/api/edge-types", json={"id": "x_test", "label_nl": "X", "label_en": "X"}
        )
    assert resp.status_code == 403


async def test_member_cannot_create_initiatief(tree: Tree, as_user):
    async with as_user(tree.member) as c:
        resp = await c.post("/api/initiatieven", json={"naam": "Stiekem"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Chat write tools
# ---------------------------------------------------------------------------


async def test_chat_add_stakeholder_needs_permission(tree: Tree):
    from bouwmeester.services.chat_service import _execute_write_tool

    node = CorpusNode(id=uuid.uuid4(), title="N", node_type="dossier", status="actief")
    tree.db.add(node)
    await tree.db.flush()

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


async def test_chat_add_stakeholder_rejects_unknown_rol(tree: Tree):
    from bouwmeester.services.chat_service import _execute_write_tool

    node = CorpusNode(id=uuid.uuid4(), title="N", node_type="dossier", status="actief")
    tree.db.add(node)
    await tree.db.flush()

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
    victim_email = (
        await tree.db.scalar(
            select(PersonEmail.email).where(PersonEmail.person_id == tree.contact.id)
        )
    ) or ""
    person = await get_or_create_person(
        tree.db, sub="attacker-sub", email=victim_email, name="A", email_verified=False
    )
    assert person.id != tree.contact.id


async def test_verified_email_does_not_rebind_other_subject(tree: Tree):
    email = await tree.db.scalar(
        select(PersonEmail.email).where(PersonEmail.person_id == tree.member.id)
    )
    person = await get_or_create_person(
        tree.db, sub="second-idp-account", email=email, name="B", email_verified=True
    )
    assert person.id != tree.member.id
    await tree.db.refresh(tree.member)
    assert tree.member.oidc_subject != "second-idp-account"


async def test_verified_email_links_unbound_person(tree: Tree):
    email = await tree.db.scalar(
        select(PersonEmail.email).where(PersonEmail.person_id == tree.contact.id)
    )
    person = await get_or_create_person(
        tree.db, sub="contact-sub", email=email, name="C", email_verified=True
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


async def test_admin_user_fails_closed_without_person():
    settings = SimpleNamespace(OIDC_ISSUER="https://idp.example")
    with patch("bouwmeester.core.auth._resolve_user", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await get_admin_user(_fake_request("/api/admin/whitelist"), None, settings)
    assert exc.value.status_code == 401


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
