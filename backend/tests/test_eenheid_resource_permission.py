"""Tests for eenheid-scoped resource permissions on initiatieven.

Access levels come from ``core.authz`` via ``initiatief_access_level``.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.initiatief_context import initiatief_access_level
from bouwmeester.core.permissions import build_permission_context
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.schema.initiatief import InitiatiefCreate
from tests.factories import make_org, make_person


@pytest.fixture
async def eenheid_rp_setup(db_session: AsyncSession):
    """Setup: person in eenheid, initiatief, eenheid linked to initiatief."""
    org = await make_org(db_session, "Test Directie")
    person = await make_person(db_session, "Eenheid User", account=False)

    # Person is member of org
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=org.id,
            start_datum=date.today() - timedelta(days=30),
        )
    )
    # Editor on the org: counts only on initiatieven that org owns
    db_session.add(
        PersonRole(
            person_id=person.id,
            role_id="editor",
            organisatie_eenheid_id=org.id,
            start_datum=date.today() - timedelta(days=30),
        )
    )
    await db_session.flush()

    # Create initiatief
    repo = InitiatiefRepository(db_session)
    initiatief = await repo.create(InitiatiefCreate(naam="Test Init"))

    yield {
        "db": db_session,
        "org": org,
        "person": person,
        "initiatief": initiatief,
        "repo": repo,
    }


async def _level(s) -> str | None:
    ctx = await build_permission_context(s["db"], s["person"])
    return await initiatief_access_level(s["db"], ctx, s["initiatief"].id)


async def test_add_eenheid_creates_resource_permission(eenheid_rp_setup):
    """Adding an eenheid to an initiatief creates a resource_permission row."""
    s = eenheid_rp_setup
    rp = await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "contributor")

    assert rp.organisatie_eenheid_id == s["org"].id
    assert rp.person_id is None
    assert rp.resource_type == "initiatief"
    assert rp.resource_id == s["initiatief"].id
    assert rp.rol == "contributor"


async def test_eenheid_access_level_via_resource_permission(eenheid_rp_setup):
    """Person gets access to initiatief via eenheid resource_permission."""
    s = eenheid_rp_setup

    # Link eenheid to initiatief as contributor
    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "contributor")

    # Check that person has access via eenheid
    level = await _level(s)
    assert level == "contributor"


async def test_eenheid_eigenaar_grants_higher_access(eenheid_rp_setup):
    """Eenheid with eigenaar rol gives eigenaar access."""
    s = eenheid_rp_setup

    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "eigenaar")

    level = await _level(s)
    assert level == "eigenaar"


async def test_viewer_eenheid_gives_read_access(eenheid_rp_setup):
    """A person in a linked eenheid gets access, even as viewer."""
    s = eenheid_rp_setup

    # Not a member yet
    assert await _level(s) is None

    # Link eenheid
    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "viewer")

    # Now is a member
    assert await _level(s) is not None


async def test_remove_eenheid_revokes_access(eenheid_rp_setup):
    """Removing eenheid link revokes access."""
    s = eenheid_rp_setup

    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "contributor")
    assert await _level(s) is not None

    await s["repo"].remove_eenheid(s["initiatief"].id, s["org"].id)
    assert await _level(s) is None


async def test_update_eenheid_rol(eenheid_rp_setup):
    """Updating eenheid rol changes the access level."""
    s = eenheid_rp_setup

    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "viewer")
    level = await _level(s)
    assert level == "viewer"

    await s["repo"].update_eenheid_rol(s["initiatief"].id, s["org"].id, "eigenaar")
    level = await _level(s)
    assert level == "eigenaar"


async def test_expired_eenheid_membership_no_access(eenheid_rp_setup):
    """Person with expired eenheid membership doesn't get access."""
    s = eenheid_rp_setup
    db = s["db"]

    # Link eenheid to initiatief
    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "contributor")

    # Expire the person's membership in the org
    from sqlalchemy import update

    await db.execute(
        update(PersonOrganisatieEenheid)
        .where(PersonOrganisatieEenheid.person_id == s["person"].id)
        .values(eind_datum=date.today() - timedelta(days=1))
    )
    await db.flush()

    # Person should no longer have access via eenheid
    level = await _level(s)
    assert level is None
    assert await _level(s) is None
