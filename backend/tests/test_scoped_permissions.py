"""Tests for scoped permissions in /my-permissions endpoint."""

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.org_naam import OrganisatieEenheidNaam
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
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
        headers={"Authorization": "Bearer test-scoped"},
    )
    return app, client


@pytest.fixture
async def scoped_setup(db_session: AsyncSession):
    """Editor in org_a, viewer in org_b, super_admin."""
    org_a = await _make_org(db_session, "Org Alpha")
    org_b = await _make_org(db_session, "Org Beta")

    editor = await _make_person(db_session, "Scoped Editor")
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=editor.id,
            organisatie_eenheid_id=org_a.id,
            start_datum=date.today(),
        )
    )
    db_session.add(
        PersonRole(
            person_id=editor.id,
            role_id="editor",
            organisatie_eenheid_id=org_a.id,
            start_datum=date.today() - timedelta(days=1),
        )
    )
    db_session.add(
        PersonRole(
            person_id=editor.id,
            role_id="viewer",
            organisatie_eenheid_id=org_b.id,
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db_session.flush()

    admin = await _make_person(db_session, "Super Admin")
    db_session.add(
        PersonRole(
            person_id=admin.id,
            role_id="super_admin",
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db_session.flush()

    editor_app, editor_client = _make_app_and_client(db_session, editor)
    admin_app, admin_client = _make_app_and_client(db_session, admin)

    async with editor_client, admin_client:
        yield {
            "editor_client": editor_client,
            "admin_client": admin_client,
            "editor": editor,
            "admin": admin,
            "org_a": org_a,
            "org_b": org_b,
        }

    editor_app.dependency_overrides.clear()
    admin_app.dependency_overrides.clear()


async def test_my_permissions_returns_per_eenheid_scoped_permissions(scoped_setup):
    """Editor with roles in two eenheden gets per-eenheid permission sets."""
    s = scoped_setup
    resp = await s["editor_client"].get(
        f"/api/roles/my-permissions?person_id={s['editor'].id}"
    )
    assert resp.status_code == 200
    data = resp.json()

    scoped = data.get("scoped_permissions", {})
    org_a_id = str(s["org_a"].id)
    org_b_id = str(s["org_b"].id)

    assert org_a_id in scoped, f"Expected org_a ({org_a_id}) in scoped_permissions"
    assert org_b_id in scoped, f"Expected org_b ({org_b_id}) in scoped_permissions"

    # Editor has node:create at org_a, viewer does not
    assert "node:create" in scoped[org_a_id]
    assert "node:update" in scoped[org_a_id]
    assert "node:create" not in scoped[org_b_id]

    # Viewer has read permissions at org_b
    assert "node:read" in scoped[org_b_id]


async def test_my_permissions_admin_has_empty_scoped(scoped_setup):
    """Super admin gets empty scoped_permissions."""
    s = scoped_setup
    resp = await s["admin_client"].get(
        f"/api/roles/my-permissions?person_id={s['admin'].id}"
    )
    assert resp.status_code == 200
    data = resp.json()

    scoped = data.get("scoped_permissions", {})
    assert scoped == {}


async def test_my_permissions_flat_is_union_of_scoped(scoped_setup):
    """Flat permissions list is the union of all scoped permissions."""
    s = scoped_setup
    resp = await s["editor_client"].get(
        f"/api/roles/my-permissions?person_id={s['editor'].id}"
    )
    data = resp.json()

    flat = set(data["permissions"])
    scoped = data["scoped_permissions"]

    # Every scoped permission should be in the flat set
    for perms in scoped.values():
        for p in perms:
            assert p in flat, f"{p} in scoped but not in flat permissions"

    # Editor has node:create (from org_a) in flat set
    assert "node:create" in flat
    # Viewer has node:read (from org_b) in flat set
    assert "node:read" in flat
