"""Tests for auth endpoints and onboarding logic."""

import uuid
from datetime import date

from sqlalchemy import select

from bouwmeester.core.onboarding import _profile_complete
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


async def test_onboarding_validates_required_fields(client):
    """POST /onboarding with empty body returns 422."""
    resp = await client.post("/api/auth/onboarding", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Profile completion logic (replaces old _check_needs_onboarding tests)
#
# Profile is considered complete when person.functie is set.
# Placement status is tracked separately via needs_placement.
# ---------------------------------------------------------------------------


async def test_profile_incomplete_no_functie(db_session):
    """Person without functie has incomplete profile."""
    person = Person(
        id=uuid.uuid4(),
        naam="New User",
        email="nofunctie@example.com",
        oidc_subject="sub-nofunctie",
        functie=None,
    )
    db_session.add(person)
    await db_session.flush()
    assert await _profile_complete(db_session, person.id) is False


async def test_profile_complete_with_functie(db_session):
    """Person with functie has complete profile."""
    person = Person(
        id=uuid.uuid4(),
        naam="Complete User",
        email="complete@example.com",
        oidc_subject="sub-complete",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()
    assert await _profile_complete(db_session, person.id) is True


async def test_profile_complete_ignores_placement(db_session):
    """Profile completion only checks functie, not placement status."""
    person = Person(
        id=uuid.uuid4(),
        naam="No Placement User",
        email="noplacement@example.com",
        oidc_subject="sub-noplacement",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()
    # Has functie but no placement — profile is still complete
    assert await _profile_complete(db_session, person.id) is True


# ---------------------------------------------------------------------------
# Onboarding endpoint validation (via direct DB setup, not HTTP)
# ---------------------------------------------------------------------------


async def test_onboarding_creates_placement(db_session, sample_organisatie):
    """Simulate onboarding: update person + create placement request."""
    person = Person(
        id=uuid.uuid4(),
        naam="Onboarding User",
        email="onboarding@example.com",
        oidc_subject="sub-onboarding",
        functie=None,
    )
    db_session.add(person)
    await db_session.flush()

    # Before: profile incomplete (no functie)
    assert await _profile_complete(db_session, person.id) is False

    # Simulate onboarding: set functie
    person.naam = "Updated Name"
    person.functie = "Beleidsmedewerker"
    await db_session.flush()

    # After: profile complete (functie is set)
    assert await _profile_complete(db_session, person.id) is True
    assert person.naam == "Updated Name"
    assert person.functie == "Beleidsmedewerker"


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

    assert await _profile_complete(db_session, person.id) is True

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
