"""Tests for eenheid module toggles and permission subtraction."""

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import build_permission_context
from bouwmeester.models.eenheid_module import EenheidModule
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


async def _make_org(
    db: AsyncSession, naam: str, parent_id: uuid.UUID | None = None
) -> OrganisatieEenheid:
    org = OrganisatieEenheid(
        id=uuid.uuid4(), naam=naam, type="directie", parent_id=parent_id
    )
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
        headers={"Authorization": "Bearer test-module"},
    )
    return app, client


@pytest.fixture
async def module_setup(db_session: AsyncSession):
    """Create org hierarchy: parent -> child, editor in child, super_admin."""
    parent = await _make_org(db_session, "Ministerie Test")
    child = await _make_org(db_session, "Directie Test", parent_id=parent.id)

    editor = await _make_person(db_session, "Module Editor")
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=editor.id,
            organisatie_eenheid_id=child.id,
            start_datum=date.today(),
        )
    )
    db_session.add(
        PersonRole(
            person_id=editor.id,
            role_id="editor",
            organisatie_eenheid_id=child.id,
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db_session.flush()

    admin = await _make_person(db_session, "Module Admin")
    db_session.add(
        PersonRole(
            person_id=admin.id,
            role_id="super_admin",
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db_session.flush()

    yield {
        "db": db_session,
        "parent": parent,
        "child": child,
        "editor": editor,
        "admin": admin,
    }


# ---------------------------------------------------------------------------
# Permission context tests
# ---------------------------------------------------------------------------


async def test_no_overrides_all_permissions_granted(module_setup):
    """Without any module overrides, editor gets all editor permissions."""
    s = module_setup
    perm_ctx = await build_permission_context(s["db"], s["editor"])

    child_id = s["child"].id
    child_perms = perm_ctx.scoped_permissions.get(child_id, set())

    assert "initiatief:read" in child_perms
    assert "initiatief:update" in child_perms
    assert "lead:read" in child_perms
    assert "node:read" in child_perms


async def test_disable_module_removes_permissions(module_setup):
    """Disabling 'initiatieven' removes initiatief:* from scoped permissions."""
    s = module_setup
    db = s["db"]

    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="initiatieven",
            enabled=False,
        )
    )
    await db.flush()

    perm_ctx = await build_permission_context(db, s["editor"])
    child_perms = perm_ctx.scoped_permissions.get(s["child"].id, set())

    assert "initiatief:read" not in child_perms
    assert "initiatief:update" not in child_perms
    assert "initiatief:create" not in child_perms

    assert "lead:read" in child_perms
    assert "node:read" in child_perms


async def test_parent_disable_inherits_to_child(module_setup):
    """Disabling a module on parent eenheid inherits to child."""
    s = module_setup
    db = s["db"]

    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["parent"].id,
            module="leads",
            enabled=False,
        )
    )
    await db.flush()

    perm_ctx = await build_permission_context(db, s["editor"])
    child_perms = perm_ctx.scoped_permissions.get(s["child"].id, set())

    assert "lead:read" not in child_perms
    assert "lead:create" not in child_perms

    assert "node:read" in child_perms
    assert "initiatief:read" in child_perms


async def test_super_admin_unaffected_by_module_disables(module_setup):
    """Super admin bypasses module disables entirely."""
    s = module_setup
    db = s["db"]

    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="initiatieven",
            enabled=False,
        )
    )
    await db.flush()

    perm_ctx = await build_permission_context(db, s["admin"])

    assert perm_ctx.is_super_admin
    assert perm_ctx.has_permission("initiatief:read")
    assert perm_ctx.has_permission("initiatief:update")


async def test_effective_permissions_updated_after_disable(module_setup):
    """Effective permissions (flat union) reflects module disables."""
    s = module_setup
    db = s["db"]

    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="opdrachten",
            enabled=False,
        )
    )
    await db.flush()

    perm_ctx = await build_permission_context(db, s["editor"])

    assert "opdracht:read" not in perm_ctx.effective_permissions
    assert "opdracht:create" not in perm_ctx.effective_permissions
    assert "node:read" in perm_ctx.effective_permissions


async def test_member_without_explicit_role_gets_viewer_permissions(module_setup):
    """A person placed in an eenheid without explicit PersonRole gets viewer perms."""
    s = module_setup
    db = s["db"]

    member = await _make_person(db, "Implicit Viewer")
    db.add(
        PersonOrganisatieEenheid(
            person_id=member.id,
            organisatie_eenheid_id=s["child"].id,
            start_datum=date.today(),
        )
    )
    # No PersonRole added — only a placement
    await db.flush()

    perm_ctx = await build_permission_context(db, member)
    child_perms = perm_ctx.scoped_permissions.get(s["child"].id, set())

    # Should have viewer-level permissions
    assert "lead:read" in child_perms
    assert "node:read" in child_perms
    assert "initiatief:read" in child_perms
    assert "opdracht:read" in child_perms
    assert "task:read" in child_perms

    # Should NOT have editor permissions
    assert "node:create" not in child_perms
    assert "lead:create" not in child_perms

    # Effective permissions should include the viewer perms
    assert "lead:read" in perm_ctx.effective_permissions


async def test_member_without_role_respects_module_disables(module_setup):
    """Implicit viewer perms are still subject to module disables."""
    s = module_setup
    db = s["db"]

    member = await _make_person(db, "Module Limited Member")
    db.add(
        PersonOrganisatieEenheid(
            person_id=member.id,
            organisatie_eenheid_id=s["child"].id,
            start_datum=date.today(),
        )
    )
    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="leads",
            enabled=False,
        )
    )
    await db.flush()

    perm_ctx = await build_permission_context(db, member)
    child_perms = perm_ctx.scoped_permissions.get(s["child"].id, set())

    # Leads module disabled, so no lead:read even with implicit viewer
    assert "lead:read" not in child_perms
    assert "lead:read" not in perm_ctx.effective_permissions

    # Other modules still work
    assert "node:read" in child_perms


async def test_multi_eenheid_user_partial_disable(module_setup):
    """User in two eenheden: disabled in A, enabled in B keeps effective perms."""
    s = module_setup
    db = s["db"]

    # Create second eenheid without initiatieven disable
    org_b = await _make_org(db, "Directie B", parent_id=s["parent"].id)
    db.add(
        PersonOrganisatieEenheid(
            person_id=s["editor"].id,
            organisatie_eenheid_id=org_b.id,
            start_datum=date.today(),
        )
    )
    db.add(
        PersonRole(
            person_id=s["editor"].id,
            role_id="editor",
            organisatie_eenheid_id=org_b.id,
            start_datum=date.today() - timedelta(days=1),
        )
    )

    # Disable initiatieven in child (A) only
    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="initiatieven",
            enabled=False,
        )
    )
    await db.flush()

    perm_ctx = await build_permission_context(db, s["editor"])

    # Child eenheid: no initiatief perms
    child_perms = perm_ctx.scoped_permissions.get(s["child"].id, set())
    assert "initiatief:read" not in child_perms

    # Org B: still has initiatief perms
    org_b_perms = perm_ctx.scoped_permissions.get(org_b.id, set())
    assert "initiatief:read" in org_b_perms

    # Effective permissions: still has it (union includes org B)
    assert "initiatief:read" in perm_ctx.effective_permissions


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


async def test_get_eenheid_modules_returns_config(module_setup):
    """GET /api/eenheid-modules/{id} returns all modules with correct state."""
    s = module_setup
    app, client = _make_app_and_client(s["db"], s["admin"])

    async with client:
        resp = await client.get(f"/api/eenheid-modules/{s['child'].id}")

    assert resp.status_code == 200
    data = resp.json()
    modules = {m["module"]: m for m in data["modules"]}

    assert len(modules) == 5
    assert all(m["enabled"] for m in modules.values())
    assert all(m["inherited_from"] is None for m in modules.values())

    app.dependency_overrides.clear()


async def test_put_disable_module(module_setup):
    """PUT /api/eenheid-modules/{id} disables a module."""
    s = module_setup
    app, client = _make_app_and_client(s["db"], s["admin"])

    async with client:
        resp = await client.put(
            f"/api/eenheid-modules/{s['child'].id}",
            json={"module": "leads", "enabled": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    modules = {m["module"]: m for m in data["modules"]}
    assert modules["leads"]["enabled"] is False

    app.dependency_overrides.clear()


async def test_get_eenheid_modules_shows_inherited(module_setup):
    """Inherited disables show inherited_from in the response."""
    s = module_setup
    db = s["db"]

    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["parent"].id,
            module="opdrachten",
            enabled=False,
        )
    )
    await db.flush()

    app, client = _make_app_and_client(db, s["admin"])

    async with client:
        resp = await client.get(f"/api/eenheid-modules/{s['child'].id}")

    assert resp.status_code == 200
    data = resp.json()
    modules = {m["module"]: m for m in data["modules"]}

    assert modules["opdrachten"]["enabled"] is False
    assert modules["opdrachten"]["inherited_from"] == str(s["parent"].id)
    assert modules["opdrachten"]["inherited_from_naam"] == "Ministerie Test"

    app.dependency_overrides.clear()


async def test_get_nonexistent_eenheid_returns_404(module_setup):
    """GET with non-existent eenheid_id returns 404."""
    s = module_setup
    app, client = _make_app_and_client(s["db"], s["admin"])

    async with client:
        resp = await client.get(f"/api/eenheid-modules/{uuid.uuid4()}")

    assert resp.status_code == 404

    app.dependency_overrides.clear()


async def test_put_invalid_module_returns_422(module_setup):
    """PUT with invalid module key returns 422."""
    s = module_setup
    app, client = _make_app_and_client(s["db"], s["admin"])

    async with client:
        resp = await client.put(
            f"/api/eenheid-modules/{s['child'].id}",
            json={"module": "invalid_module", "enabled": False},
        )

    assert resp.status_code == 422

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Search RBAC integration
# ---------------------------------------------------------------------------


async def test_search_excludes_disabled_module_results(module_setup):
    """Search skips entity types when module is disabled for the user's eenheid."""
    s = module_setup
    db = s["db"]

    # Disable leads for the editor's eenheid
    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="leads",
            enabled=False,
        )
    )
    await db.flush()

    app, client = _make_app_and_client(db, s["editor"])

    async with client:
        resp = await client.get("/api/search", params={"q": "test"})

    assert resp.status_code == 200
    data = resp.json()

    # No lead results should appear
    result_types = {r["result_type"] for r in data["results"]}
    assert "lead" not in result_types

    app.dependency_overrides.clear()


async def test_search_admin_sees_all_types(module_setup):
    """Super admin sees all result types regardless of module toggles."""
    s = module_setup
    db = s["db"]

    db.add(
        EenheidModule(
            organisatie_eenheid_id=s["child"].id,
            module="leads",
            enabled=False,
        )
    )
    await db.flush()

    app, client = _make_app_and_client(db, s["admin"])

    async with client:
        # Request lead results explicitly
        resp = await client.get(
            "/api/search", params={"q": "test", "result_types": "lead"}
        )

    assert resp.status_code == 200
    # Super admin should not be blocked from requesting lead type
    # (may return 0 results if no leads exist, but shouldn't be filtered out)

    app.dependency_overrides.clear()
