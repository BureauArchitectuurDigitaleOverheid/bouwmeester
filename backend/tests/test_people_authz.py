"""Authorization tests for the people router.

Verifies that an authenticated non-admin user without ``people:read`` /
``people:manage`` cannot access the corresponding endpoints. Bypasses the
dev-mode super-admin shortcut by overriding ``get_optional_user`` and
``get_permission_context`` directly on the app.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail


@pytest.fixture
def _test_app():
    from bouwmeester.core.app import create_app

    return create_app()


def _make_client(app, db_session, person, perms: set[str]):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = lambda: person
    app.dependency_overrides[get_permission_context] = lambda: PermissionContext(
        person_id=person.id,
        is_authenticated=True,
        effective_permissions=set(perms),
    )

    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-people-authz"},
    )


@pytest.fixture
async def people_authz_setup(db_session: AsyncSession, _test_app):
    person = Person(
        id=uuid.uuid4(),
        naam="People Authz",
        email=f"pa-{uuid.uuid4().hex[:8]}@example.com",
        functie="tester",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEmail(person_id=person.id, email=person.email, is_default=True)
    )

    target = Person(
        id=uuid.uuid4(),
        naam="Doel Persoon",
        email=f"target-{uuid.uuid4().hex[:8]}@example.com",
        functie="medewerker",
        is_active=True,
    )
    db_session.add(target)
    await db_session.flush()
    db_session.add(
        PersonEmail(person_id=target.id, email=target.email, is_default=True)
    )
    await db_session.flush()

    yield {"app": _test_app, "person": person, "target": target}

    _test_app.dependency_overrides.clear()


async def test_list_people_requires_people_read(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], set()) as ac:
        resp = await ac.get("/api/people")
    assert resp.status_code == 403


async def test_list_people_allows_people_read(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], {"people:read"}) as ac:
        resp = await ac.get("/api/people")
    assert resp.status_code == 200


async def test_get_person_requires_people_read(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], set()) as ac:
        resp = await ac.get(f"/api/people/{s['target'].id}")
    assert resp.status_code == 403


async def test_get_person_summary_requires_people_read(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], set()) as ac:
        resp = await ac.get(f"/api/people/{s['target'].id}/summary")
    assert resp.status_code == 403


async def test_create_person_requires_people_manage(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], {"people:read"}) as ac:
        resp = await ac.post("/api/people", json={"naam": "Nieuwe Persoon"})
    assert resp.status_code == 403


async def test_update_person_requires_people_update(
    people_authz_setup, db_session: AsyncSession
):
    """A user with only people:read cannot update a person."""
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], {"people:read"}) as ac:
        resp = await ac.put(
            f"/api/people/{s['target'].id}", json={"functie": "iets anders"}
        )
    assert resp.status_code == 403


async def test_update_person_allowed_with_people_update(
    people_authz_setup, db_session: AsyncSession
):
    """A user with people:update can update basic person fields."""
    s = people_authz_setup
    async with _make_client(
        s["app"], db_session, s["person"], {"people:read", "people:update"}
    ) as ac:
        resp = await ac.put(
            f"/api/people/{s['target'].id}", json={"functie": "nieuwe functie"}
        )
    assert resp.status_code == 200
    assert resp.json()["functie"] == "nieuwe functie"


async def test_delete_person_requires_people_manage(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], {"people:read"}) as ac:
        resp = await ac.delete(f"/api/people/{s['target'].id}")
    assert resp.status_code == 403


async def test_add_organisatie_requires_people_manage(
    people_authz_setup, db_session: AsyncSession
):
    s = people_authz_setup
    async with _make_client(s["app"], db_session, s["person"], {"people:read"}) as ac:
        resp = await ac.post(
            f"/api/people/{s['target'].id}/organisaties",
            json={
                "organisatie_eenheid_id": str(uuid.uuid4()),
                "start_datum": "2025-01-01",
            },
        )
    assert resp.status_code == 403
