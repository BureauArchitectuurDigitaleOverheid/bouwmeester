"""Authorization tests for the parlementair router.

Verifies that an authenticated non-admin user without the
``parlementair:read`` / ``parlementair:review`` / ``parlementair:import``
permissions cannot access the corresponding endpoints.

The dev-mode super-admin shortcut (no OIDC) is bypassed by overriding
``get_optional_user`` and ``get_permission_context`` directly on the app.
"""

import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail


@pytest.fixture
def _test_app():
    from bouwmeester.core.app import create_app

    return create_app()


def _make_client(app, db_session, person, perms: set[str]):
    """Build a client where the user has exactly *perms* (and nothing else)."""

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
        headers={"Authorization": "Bearer test-parlementair-authz"},
    )


@pytest.fixture
async def parlementair_authz_setup(db_session: AsyncSession, _test_app):
    person = Person(
        id=uuid.uuid4(),
        naam="Parlementair Tester",
        email=f"parl-{uuid.uuid4().hex[:8]}@example.com",
        functie="tester",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEmail(person_id=person.id, email=person.email, is_default=True)
    )
    await db_session.flush()

    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-99",
        titel="Authz testmotie",
        onderwerp="Authz",
        bron="tweede_kamer",
        datum=date(2024, 6, 15),
        status="pending",
    )
    db_session.add(item)
    await db_session.flush()

    yield {"app": _test_app, "person": person, "item": item}

    _test_app.dependency_overrides.clear()


async def test_list_imports_requires_parlementair_read(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user without parlementair:read gets 403 on GET /imports."""
    s = parlementair_authz_setup
    async with _make_client(s["app"], db_session, s["person"], set()) as ac:
        resp = await ac.get("/api/parlementair/imports")
    assert resp.status_code == 403


async def test_list_imports_allows_parlementair_read(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user with parlementair:read sees the imports list."""
    s = parlementair_authz_setup

    async def _override_get_db():
        yield db_session

    s["app"].dependency_overrides[get_db] = _override_get_db

    async with _make_client(
        s["app"], db_session, s["person"], {"parlementair:read"}
    ) as ac:
        resp = await ac.get("/api/parlementair/imports")
    assert resp.status_code == 200
    ids = {x["id"] for x in resp.json()}
    assert str(s["item"].id) in ids


async def test_trigger_import_requires_parlementair_import(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user with only parlementair:read cannot trigger an import."""
    s = parlementair_authz_setup

    async def _override_get_db():
        yield db_session

    s["app"].dependency_overrides[get_db] = _override_get_db

    async with _make_client(
        s["app"], db_session, s["person"], {"parlementair:read"}
    ) as ac:
        resp = await ac.post("/api/parlementair/imports/trigger")
    assert resp.status_code == 403


async def test_reject_import_requires_parlementair_review(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user with only parlementair:read cannot reject an import."""
    s = parlementair_authz_setup

    async def _override_get_db():
        yield db_session

    s["app"].dependency_overrides[get_db] = _override_get_db

    async with _make_client(
        s["app"], db_session, s["person"], {"parlementair:read"}
    ) as ac:
        resp = await ac.put(f"/api/parlementair/imports/{s['item'].id}/reject")
    assert resp.status_code == 403
