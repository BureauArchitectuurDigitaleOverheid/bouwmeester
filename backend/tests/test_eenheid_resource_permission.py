"""Tests for eenheid-scoped resource permissions on initiatieven."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.org_naam import OrganisatieEenheidNaam
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.schema.initiatief import InitiatiefCreate


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
async def eenheid_rp_setup(db_session: AsyncSession):
    """Setup: person in eenheid, initiatief, eenheid linked to initiatief."""
    org = await _make_org(db_session, "Test Directie")
    person = await _make_person(db_session, "Eenheid User")

    # Person is member of org
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=org.id,
            start_datum=date.today() - timedelta(days=30),
        )
    )
    # Person has editor role (for RBAC baseline)
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
    level = await s["repo"].get_eenheid_access_level(s["initiatief"].id, s["person"].id)
    assert level == "contributor"


async def test_eenheid_eigenaar_grants_higher_access(eenheid_rp_setup):
    """Eenheid with eigenaar rol gives eigenaar access."""
    s = eenheid_rp_setup

    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "eigenaar")

    level = await s["repo"].get_eenheid_access_level(s["initiatief"].id, s["person"].id)
    assert level == "eigenaar"


async def test_is_member_via_eenheid(eenheid_rp_setup):
    """is_member returns True when person is in a linked eenheid."""
    s = eenheid_rp_setup

    # Not a member yet
    assert not await s["repo"].is_member(s["initiatief"].id, s["person"].id)

    # Link eenheid
    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "viewer")

    # Now is a member
    assert await s["repo"].is_member(s["initiatief"].id, s["person"].id)


async def test_remove_eenheid_revokes_access(eenheid_rp_setup):
    """Removing eenheid link revokes access."""
    s = eenheid_rp_setup

    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "contributor")
    assert await s["repo"].is_member(s["initiatief"].id, s["person"].id)

    await s["repo"].remove_eenheid(s["initiatief"].id, s["org"].id)
    assert not await s["repo"].is_member(s["initiatief"].id, s["person"].id)


async def test_update_eenheid_rol(eenheid_rp_setup):
    """Updating eenheid rol changes the access level."""
    s = eenheid_rp_setup

    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "viewer")
    level = await s["repo"].get_eenheid_access_level(s["initiatief"].id, s["person"].id)
    assert level == "viewer"

    await s["repo"].update_eenheid_rol(s["initiatief"].id, s["org"].id, "eigenaar")
    level = await s["repo"].get_eenheid_access_level(s["initiatief"].id, s["person"].id)
    assert level == "eigenaar"


async def test_list_eenheden_returns_only_eenheid_scoped(eenheid_rp_setup):
    """list_eenheden returns only eenheid-scoped permissions, not person-scoped."""
    s = eenheid_rp_setup

    # Add both person and eenheid permissions
    await s["repo"].add_member(s["initiatief"].id, s["person"].id, "eigenaar")
    await s["repo"].add_eenheid(s["initiatief"].id, s["org"].id, "contributor")

    eenheden = await s["repo"].list_eenheden(s["initiatief"].id)
    assert len(eenheden) == 1
    assert eenheden[0].organisatie_eenheid_id == s["org"].id
    assert eenheden[0].person_id is None


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
    level = await s["repo"].get_eenheid_access_level(s["initiatief"].id, s["person"].id)
    assert level is None
    assert not await s["repo"].is_member(s["initiatief"].id, s["person"].id)
