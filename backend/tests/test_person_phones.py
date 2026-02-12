"""Tests for person phone CRUD endpoints."""

import uuid


async def test_add_phone(client, sample_person):
    """POST /api/people/{id}/phones adds a phone number."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612345678", "label": "werk"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["phone_number"] == "+31612345678"
    assert data["label"] == "werk"
    assert data["is_default"] is True  # first phone auto-defaults


async def test_add_second_phone_not_default(client, sample_person):
    """Second phone added is not auto-default."""
    resp1 = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612345001", "label": "werk"},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612345002", "label": "mobiel"},
    )
    assert resp2.status_code == 201
    assert resp2.json()["is_default"] is False


async def test_add_phone_invalid_label(client, sample_person):
    """Adding a phone with an invalid label returns 422."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612345000", "label": "onbekend"},
    )
    assert resp.status_code == 422


async def test_add_phone_person_not_found(client):
    """Adding phone to non-existent person returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/people/{fake_id}/phones",
        json={"phone_number": "+31612345000", "label": "werk"},
    )
    assert resp.status_code == 404


async def test_remove_phone(client, sample_person):
    """DELETE /api/people/{id}/phones/{phone_id} removes the phone."""
    add_resp = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31611111111", "label": "prive"},
    )
    assert add_resp.status_code == 201
    phone_id = add_resp.json()["id"]

    del_resp = await client.delete(f"/api/people/{sample_person.id}/phones/{phone_id}")
    assert del_resp.status_code == 204


async def test_remove_phone_not_found(client, sample_person):
    """Removing a non-existent phone returns 404."""
    fake_phone_id = uuid.uuid4()
    resp = await client.delete(f"/api/people/{sample_person.id}/phones/{fake_phone_id}")
    assert resp.status_code == 404


async def test_set_default_phone(client, sample_person):
    """POST /api/people/{id}/phones/{phone_id}/set-default sets the default."""
    # Add two phones
    resp1 = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612345001", "label": "werk"},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612345002", "label": "mobiel"},
    )
    assert resp2.status_code == 201
    second_phone_id = resp2.json()["id"]

    # Set second phone as default
    resp = await client.post(
        f"/api/people/{sample_person.id}/phones/{second_phone_id}/set-default"
    )
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True
    assert resp.json()["phone_number"] == "+31612345002"


async def test_set_default_phone_not_found(client, sample_person):
    """Setting default on non-existent phone returns 404."""
    fake_phone_id = uuid.uuid4()
    resp = await client.post(
        f"/api/people/{sample_person.id}/phones/{fake_phone_id}/set-default"
    )
    assert resp.status_code == 404


async def test_person_response_includes_phones(client, sample_person):
    """GET /api/people/{id} includes phones in response after adding one."""
    # Add a phone first
    add_resp = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "+31612349999", "label": "werk"},
    )
    assert add_resp.status_code == 201

    resp = await client.get(f"/api/people/{sample_person.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "phones" in data
    assert len(data["phones"]) >= 1
    assert data["default_phone"] == "+31612349999"


async def test_phone_normalized_to_e164(client, sample_person):
    """Local Dutch number is normalized to E.164 format."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "0612345678", "label": "mobiel"},
    )
    assert resp.status_code == 201
    assert resp.json()["phone_number"] == "+31612345678"


async def test_phone_invalid_number_rejected(client, sample_person):
    """Invalid phone number is rejected with 422."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/phones",
        json={"phone_number": "123", "label": "werk"},
    )
    assert resp.status_code == 422
