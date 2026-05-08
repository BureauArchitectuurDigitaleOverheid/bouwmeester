"""Editors can create stakeholder eenheden anywhere in the tree.

Covers the scenario from the lead-stakeholder flow: a Bewerker (editor
role) without ministry_admin needs to add an org unit for a counterpart
that does not fall under their own ministry. The aanmaker is granted
an eigenaar resource-permission so they can edit/delete that eenheid
later, even though it is outside their visible org scope.
"""

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.org_naam import OrganisatieEenheidNaam
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole


async def _make_person(db: AsyncSession, naam: str) -> Person:
    uid = uuid.uuid4()
    email = f"{naam.lower().replace(' ', '-')}-{uid.hex[:8]}@example.com"
    person = Person(id=uid, naam=naam, email=email, functie="tester", is_active=True)
    db.add(person)
    await db.flush()
    db.add(PersonEmail(person_id=person.id, email=email, is_default=True))
    await db.flush()
    return person


async def _make_org(db: AsyncSession, naam: str) -> OrganisatieEenheid:
    org = OrganisatieEenheid(id=uuid.uuid4(), naam=naam, type="directie")
    db.add(org)
    await db.flush()
    db.add(
        OrganisatieEenheidNaam(eenheid_id=org.id, naam=naam, geldig_van=date.today())
    )
    await db.flush()
    return org


def _make_app_and_client(db_session, person):
    from bouwmeester.core.app import create_app

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = lambda: person

    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-editor-create"},
    )
    return app, client


@pytest.fixture
async def editor_setup(db_session: AsyncSession):
    """Editor on org_own, plus a separate org_other outside their scope."""
    org_own = await _make_org(db_session, "Eigen Directie")
    org_other = await _make_org(db_session, "Ander Ministerie")

    editor = await _make_person(db_session, "Abram Bewerker")
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=editor.id,
            organisatie_eenheid_id=org_own.id,
            start_datum=date.today(),
        )
    )
    db_session.add(
        PersonRole(
            person_id=editor.id,
            role_id="editor",
            organisatie_eenheid_id=org_own.id,
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db_session.flush()

    app, client = _make_app_and_client(db_session, editor)
    async with client:
        yield {
            "client": client,
            "editor": editor,
            "org_own": org_own,
            "org_other": org_other,
        }
    app.dependency_overrides.clear()


async def test_editor_creates_top_level_eenheid(editor_setup):
    """Editor without parent_id creates a new top-level org unit."""
    s = editor_setup
    resp = await s["client"].post(
        "/api/organisatie",
        json={"naam": "CJIB", "type": "ministerie"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["naam"] == "CJIB"
    assert body["parent_id"] is None


async def test_editor_creates_eenheid_under_foreign_parent(editor_setup):
    """Editor can hang a new eenheid under a parent outside their scope."""
    s = editor_setup
    resp = await s["client"].post(
        "/api/organisatie",
        json={
            "naam": "CJIB",
            "type": "directie",
            "parent_id": str(s["org_other"].id),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["parent_id"] == str(s["org_other"].id)


async def test_aanmaker_gets_eigenaar_resource_permission(
    editor_setup, db_session: AsyncSession
):
    """Creating an eenheid grants the aanmaker an eigenaar resource-permission."""
    s = editor_setup
    resp = await s["client"].post(
        "/api/organisatie",
        json={"naam": "Stakeholder X", "type": "directie"},
    )
    assert resp.status_code == 201
    new_id = uuid.UUID(resp.json()["id"])

    rp = (
        await db_session.execute(
            select(ResourcePermission).where(
                ResourcePermission.person_id == s["editor"].id,
                ResourcePermission.resource_type == "organisatie_eenheid",
                ResourcePermission.resource_id == new_id,
            )
        )
    ).scalar_one()
    assert rp.rol == "eigenaar"


async def test_aanmaker_can_update_own_eenheid_outside_scope(editor_setup):
    """The eigenaar resource-permission unlocks update on out-of-scope eenheden."""
    s = editor_setup
    create = await s["client"].post(
        "/api/organisatie",
        json={"naam": "CJIB", "type": "ministerie"},
    )
    new_id = create.json()["id"]

    upd = await s["client"].put(
        f"/api/organisatie/{new_id}",
        json={"naam": "CJIB (hoofd)"},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["naam"] == "CJIB (hoofd)"


async def test_editor_cannot_update_unrelated_foreign_eenheid(editor_setup):
    """Editor with no resource-permission on a foreign eenheid is blocked."""
    s = editor_setup
    upd = await s["client"].put(
        f"/api/organisatie/{s['org_other'].id}",
        json={"naam": "Geprobeerd te kapen"},
    )
    assert upd.status_code == 403


async def test_aanmaker_can_delete_own_eenheid_outside_scope(editor_setup):
    """Eigenaar resource-permission also allows delete."""
    s = editor_setup
    create = await s["client"].post(
        "/api/organisatie",
        json={"naam": "Tijdelijk", "type": "directie"},
    )
    new_id = create.json()["id"]

    delete = await s["client"].delete(f"/api/organisatie/{new_id}")
    assert delete.status_code == 204


async def test_editor_has_org_create_but_not_org_manage(
    editor_setup, db_session: AsyncSession
):
    """Regression-guard: editor must have org:create, not org:manage.

    org:manage gates the AdminPage > Organisatie tab in the frontend, so
    granting it to editors would unintentionally expose admin UI. Failing
    this test means the design has drifted.
    """
    from bouwmeester.repositories.role import RoleRepository

    perms = await RoleRepository(db_session).get_role_permission_ids("editor")
    assert "org:create" in perms
    assert "org:manage" not in perms
