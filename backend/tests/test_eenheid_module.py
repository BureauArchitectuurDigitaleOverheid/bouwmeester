"""Tests for eenheid module toggles and permission subtraction."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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


@pytest.fixture
async def module_setup(db_session: AsyncSession):
    """Create org hierarchy: parent → child, editor in child, super_admin."""
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

    # Disable initiatieven for the child eenheid
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

    # Initiatief permissions should be removed
    assert "initiatief:read" not in child_perms
    assert "initiatief:update" not in child_perms
    assert "initiatief:create" not in child_perms

    # Other permissions should remain
    assert "lead:read" in child_perms
    assert "node:read" in child_perms


async def test_parent_disable_inherits_to_child(module_setup):
    """Disabling a module on parent eenheid inherits to child."""
    s = module_setup
    db = s["db"]

    # Disable leads on the PARENT
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

    # Lead permissions should be removed (inherited from parent)
    assert "lead:read" not in child_perms
    assert "lead:create" not in child_perms

    # Non-disabled modules still work
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

    # Super admin should still have all permissions
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

    # The editor only has one eenheid, so effective should also lack opdracht:*
    assert "opdracht:read" not in perm_ctx.effective_permissions
    assert "opdracht:create" not in perm_ctx.effective_permissions

    # Other permissions still in effective set
    assert "node:read" in perm_ctx.effective_permissions
