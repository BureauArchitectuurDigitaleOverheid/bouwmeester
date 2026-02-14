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
        json={"email": sample_person.email},  # already exists from fixture
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
    assert data["emails"][0]["email"] == sample_person.email
    assert data["default_email"] == sample_person.email


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


async def test_delete_default_email_promotes_next(client, sample_person):
    """Deleting the default email auto-promotes another one."""
    # Add email and set as default
    resp1 = await client.post(
        f"/api/people/{sample_person.id}/emails",
        json={"email": "extra-default@example.com", "is_default": True},
    )
    assert resp1.status_code == 201
    extra_id = resp1.json()["id"]

    # Delete the default
    del_resp = await client.delete(f"/api/people/{sample_person.id}/emails/{extra_id}")
    assert del_resp.status_code == 204

    # Another email should now be default (the fixture's or another remaining one)
    person_resp = await client.get(f"/api/people/{sample_person.id}")
    data = person_resp.json()
    remaining_emails = data["emails"]
    assert len(remaining_emails) >= 1
    defaults = [e for e in remaining_emails if e["is_default"]]
    assert len(defaults) == 1, "Exactly one email should be default after deletion"
