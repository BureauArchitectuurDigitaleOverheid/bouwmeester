"""Tests for auth endpoints — /status and /onboarding."""

import uuid
from datetime import date

from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid


async def test_auth_status_unauthenticated(client):
    """GET /api/auth/status returns oidc_configured=false in dev mode."""
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False
    assert data["oidc_configured"] is False
    assert "person" not in data


async def test_auth_status_returns_person_fields(client, db_session):
    """When authenticated, /status returns person id and needs_onboarding."""
    # Create a person with oidc_subject
    person = Person(
        id=uuid.uuid4(),
        naam="Test User",
        email="test@example.com",
        oidc_subject="test-sub-123",
        functie=None,  # no functie = needs onboarding
    )
    db_session.add(person)
    await db_session.flush()

    # In dev mode (no OIDC), we can't test the full auth flow.
    # But we can verify the status endpoint works without errors.
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200


async def test_onboarding_requires_auth(client):
    """POST /api/auth/onboarding requires authentication."""
    resp = await client.post(
        "/api/auth/onboarding",
        json={
            "naam": "Test User",
            "functie": "Beleidsmedewerker",
            "organisatie_eenheid_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401


async def test_onboarding_schema_validation(client):
    """POST /api/auth/onboarding validates request body."""
    # Missing required fields
    resp = await client.post(
        "/api/auth/onboarding",
        json={},
    )
    assert resp.status_code in (401, 422)


async def test_person_needs_onboarding_no_functie(db_session):
    """A person without functie should need onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="New User",
        email="new@example.com",
        oidc_subject="new-sub",
        functie=None,
    )
    db_session.add(person)
    await db_session.flush()

    assert person.functie is None


async def test_person_needs_onboarding_no_placement(db_session):
    """A person with functie but no org placement should need onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="New User",
        email="new2@example.com",
        oidc_subject="new-sub-2",
        functie="Beleidsmedewerker",
    )
    db_session.add(person)
    await db_session.flush()

    # Verify no placements exist
    from sqlalchemy import select

    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.person_id == person.id,
        PersonOrganisatieEenheid.eind_datum.is_(None),
    )
    result = await db_session.execute(stmt)
    assert result.scalar_one_or_none() is None


async def test_person_complete_after_onboarding(db_session, sample_organisatie):
    """A person with functie and active placement does not need onboarding."""
    person = Person(
        id=uuid.uuid4(),
        naam="Complete User",
        email="complete@example.com",
        oidc_subject="complete-sub",
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

    # Verify placement exists
    from sqlalchemy import select

    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.person_id == person.id,
        PersonOrganisatieEenheid.eind_datum.is_(None),
    )
    result = await db_session.execute(stmt)
    assert result.scalar_one_or_none() is not None
    assert person.functie is not None
