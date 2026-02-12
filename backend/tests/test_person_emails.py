"""Tests for person email CRUD endpoints."""

import uuid


async def test_add_email(client, sample_person):
    """POST /api/people/{id}/emails adds an email."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/emails",
        json={"email": "jan-extra@example.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "jan-extra@example.com"
    assert data["is_default"] is False  # existing default stays


async def test_add_first_email_auto_default(client, db_session):
    """First email added to a person without emails becomes default."""
    from bouwmeester.models.person import Person

    person = Person(
        id=uuid.uuid4(),
        naam="Leeg Persoon",
        functie="test",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()

    resp = await client.post(
        f"/api/people/{person.id}/emails",
        json={"email": "leeg@example.com"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_default"] is True


async def test_add_email_duplicate_409(client, sample_person):
    """Adding an email that already exists returns 409."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/emails",
        json={"email": "jan@example.com"},  # already exists from fixture
    )
    assert resp.status_code == 409


async def test_add_email_person_not_found(client):
    """Adding email to non-existent person returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/people/{fake_id}/emails",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 404


async def test_remove_email(client, sample_person):
    """DELETE /api/people/{id}/emails/{email_id} removes the email."""
    # Add a second email first
    add_resp = await client.post(
        f"/api/people/{sample_person.id}/emails",
        json={"email": "jan-remove@example.com"},
    )
    assert add_resp.status_code == 201
    email_id = add_resp.json()["id"]

    del_resp = await client.delete(f"/api/people/{sample_person.id}/emails/{email_id}")
    assert del_resp.status_code == 204


async def test_remove_email_not_found(client, sample_person):
    """Removing a non-existent email returns 404."""
    fake_email_id = uuid.uuid4()
    resp = await client.delete(f"/api/people/{sample_person.id}/emails/{fake_email_id}")
    assert resp.status_code == 404


async def test_set_default_email(client, sample_person):
    """POST /api/people/{id}/emails/{email_id}/set-default sets the default."""
    # Add a second email
    add_resp = await client.post(
        f"/api/people/{sample_person.id}/emails",
        json={"email": "jan-new-default@example.com"},
    )
    assert add_resp.status_code == 201
    new_email_id = add_resp.json()["id"]

    # Set it as default
    resp = await client.post(
        f"/api/people/{sample_person.id}/emails/{new_email_id}/set-default"
    )
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True
    assert resp.json()["email"] == "jan-new-default@example.com"


async def test_set_default_email_not_found(client, sample_person):
    """Setting default on non-existent email returns 404."""
    fake_email_id = uuid.uuid4()
    resp = await client.post(
        f"/api/people/{sample_person.id}/emails/{fake_email_id}/set-default"
    )
    assert resp.status_code == 404


async def test_person_response_includes_emails(client, sample_person):
    """GET /api/people/{id} includes emails in response."""
    resp = await client.get(f"/api/people/{sample_person.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "emails" in data
    assert len(data["emails"]) >= 1
    assert data["emails"][0]["email"] == "jan@example.com"
    assert data["default_email"] == "jan@example.com"


async def test_create_person_creates_email(client):
    """POST /api/people with email also creates a PersonEmail row."""
    resp = await client.post(
        "/api/people",
        json={
            "naam": "Email Test",
            "email": "emailtest@example.com",
            "functie": "test",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["emails"]) == 1
    assert data["emails"][0]["email"] == "emailtest@example.com"
    assert data["emails"][0]["is_default"] is True
    assert data["default_email"] == "emailtest@example.com"
