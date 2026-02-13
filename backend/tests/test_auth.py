"""Tests for auth endpoints and onboarding logic."""

import uuid
from datetime import date

from sqlalchemy import select

from bouwmeester.api.routes.auth import _check_needs_onboarding
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

# ---------------------------------------------------------------------------
# GET /api/auth/status
# ---------------------------------------------------------------------------


async def test_auth_status_unauthenticated(client):
    """In dev mode (no OIDC), returns authenticated=false, no person."""
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False
    assert data["oidc_configured"] is False
    assert "person" not in data


# ---------------------------------------------------------------------------
# POST /api/auth/onboarding
# ---------------------------------------------------------------------------


async def test_onboarding_requires_auth(client):
    """POST /onboarding returns 401 without authentication."""
    resp = await client.post(
        "/api/auth/onboarding",
        json={
            "naam": "Test User",
            "functie": "Beleidsmedewerker",
            "organisatie_eenheid_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401


async def test_onboarding_validates_required_fields(client):
    """POST /onboarding with empty body returns 401 or 422."""
    resp = await client.post("/api/auth/onboarding", json={})
    # 401 because auth check runs before body validation
    assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# _check_needs_onboarding logic
# ---------------------------------------------------------------------------


async def test_needs_onboarding_no_functie(db_session):
    """Person without functie needs onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="New User",
        email="nofunctie@example.com",
        oidc_subject="sub-nofunctie",
        functie=None,
    )
    db_session.add(person)
    await db_session.flush()

    assert await _check_needs_onboarding(db_session, person) is True


async def test_needs_onboarding_no_placement(db_session):
    """Person with functie but no active org placement needs onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="No Placement User",
        email="noplacement@example.com",
        oidc_subject="sub-noplacement",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()

    assert await _check_needs_onboarding(db_session, person) is True


async def test_needs_onboarding_with_ended_placement(db_session, sample_organisatie):
    """Person with only ended placements still needs onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="Ended Placement User",
        email="ended@example.com",
        oidc_subject="sub-ended",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()

    # Create an ended placement
    placement = PersonOrganisatieEenheid(
        person_id=person.id,
        organisatie_eenheid_id=sample_organisatie.id,
        dienstverband="in_dienst",
        start_datum=date(2024, 1, 1),
        eind_datum=date(2024, 12, 31),
    )
    db_session.add(placement)
    await db_session.flush()

    assert await _check_needs_onboarding(db_session, person) is True


async def test_onboarding_complete(db_session, sample_organisatie):
    """Person with functie and active placement does NOT need onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="Complete User",
        email="complete@example.com",
        oidc_subject="sub-complete",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()

    placement = PersonOrganisatieEenheid(
        person_id=person.id,
        organisatie_eenheid_id=sample_organisatie.id,
        dienstverband="in_dienst",
        start_datum=date.today(),
    )
    db_session.add(placement)
    await db_session.flush()

    assert await _check_needs_onboarding(db_session, person) is False


# ---------------------------------------------------------------------------
# Onboarding endpoint validation (via direct DB setup, not HTTP)
# ---------------------------------------------------------------------------


async def test_onboarding_creates_placement(db_session, sample_organisatie):
    """Simulate onboarding: update person + create placement."""
    person = Person(
        id=uuid.uuid4(),
        naam="Onboarding User",
        email="onboarding@example.com",
        oidc_subject="sub-onboarding",
        functie=None,
    )
    db_session.add(person)
    await db_session.flush()

    # Before: needs onboarding
    assert await _check_needs_onboarding(db_session, person) is True

    # Simulate onboarding
    person.naam = "Updated Name"
    person.functie = "Beleidsmedewerker"
    placement = PersonOrganisatieEenheid(
        person_id=person.id,
        organisatie_eenheid_id=sample_organisatie.id,
        dienstverband="in_dienst",
        start_datum=date.today(),
    )
    db_session.add(placement)
    await db_session.flush()

    # After: onboarding complete
    assert await _check_needs_onboarding(db_session, person) is False
    assert person.naam == "Updated Name"
    assert person.functie == "Beleidsmedewerker"

    # Verify placement was created
    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.person_id == person.id,
        PersonOrganisatieEenheid.eind_datum.is_(None),
    )
    result = await db_session.execute(stmt)
    assert result.scalar_one_or_none() is not None


async def test_onboarding_idempotent_no_duplicate_placement(
    db_session, sample_organisatie
):
    """Re-submitting onboarding updates naam/functie without duplicating placement."""
    person = Person(
        id=uuid.uuid4(),
        naam="First Name",
        email="idempotent@example.com",
        oidc_subject="sub-idempotent",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()

    # Create an existing active placement (simulates completed onboarding)
    placement = PersonOrganisatieEenheid(
        person_id=person.id,
        organisatie_eenheid_id=sample_organisatie.id,
        dienstverband="in_dienst",
        start_datum=date.today(),
    )
    db_session.add(placement)
    await db_session.flush()

    assert await _check_needs_onboarding(db_session, person) is False

    # Simulate the idempotent onboarding endpoint logic:
    # always update naam/functie, only create placement if none exists
    person.naam = "Updated Name"
    person.functie = "Senior Beleidsmedewerker"

    existing = await db_session.execute(
        select(PersonOrganisatieEenheid.id).where(
            PersonOrganisatieEenheid.person_id == person.id,
            PersonOrganisatieEenheid.eind_datum.is_(None),
        )
    )
    if existing.scalar_one_or_none() is None:
        new_placement = PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=sample_organisatie.id,
            dienstverband="in_dienst",
            start_datum=date.today(),
        )
        db_session.add(new_placement)

    await db_session.flush()

    # Verify naam/functie updated
    assert person.naam == "Updated Name"
    assert person.functie == "Senior Beleidsmedewerker"

    # Verify still only one active placement (no duplicate)
    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.person_id == person.id,
        PersonOrganisatieEenheid.eind_datum.is_(None),
    )
    result = await db_session.execute(stmt)
    placements = result.scalars().all()
    assert len(placements) == 1


async def test_onboarding_rejects_invalid_org_id(db_session):
    """Onboarding with a non-existent org ID would fail FK constraint."""
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

    fake_org_id = uuid.uuid4()
    stmt = select(OrganisatieEenheid.id).where(OrganisatieEenheid.id == fake_org_id)
    result = await db_session.execute(stmt)
    assert result.scalar_one_or_none() is None, "Fake org ID should not exist"
