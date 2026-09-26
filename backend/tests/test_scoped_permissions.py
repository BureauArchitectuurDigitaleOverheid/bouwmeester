"""Tests for the /my-permissions endpoint with roles in several eenheden."""

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole
from tests.factories import make_org, make_person


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
    org_a = await make_org(db_session, "Org Alpha")
    org_b = await make_org(db_session, "Org Beta")

    editor = await make_person(db_session, "Scoped Editor", account=False)
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

    admin = await make_person(db_session, "Super Admin", account=False)
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


async def test_my_permissions_lists_permissions_from_every_eenheid(scoped_setup):
    """The flat list holds what the editor has in each eenheid.

    Per-eenheid rights (with inheritance down the tree) are decided in
    ``core.authority``; the endpoint no longer ships a per-eenheid map that
    would ignore that inheritance.
    """
    s = scoped_setup
    resp = await s["editor_client"].get(
        f"/api/roles/my-permissions?person_id={s['editor'].id}"
    )
    assert resp.status_code == 200
    data = resp.json()

    flat = set(data["permissions"])
    assert "node:create" in flat  # editor at org_a
    assert "node:read" in flat  # viewer at org_b
    assert "scoped_permissions" not in data


async def test_my_permissions_system_permissions_only_from_system_roles(
    scoped_setup,
):
    """Scoped roles never show up as system permissions; super_admin gets none."""
    s = scoped_setup
    editor = (
        await s["editor_client"].get(
            f"/api/roles/my-permissions?person_id={s['editor'].id}"
        )
    ).json()
    admin = (
        await s["admin_client"].get(
            f"/api/roles/my-permissions?person_id={s['admin'].id}"
        )
    ).json()

    assert editor["system_permissions"] == []
    assert admin["system_permissions"] == []
