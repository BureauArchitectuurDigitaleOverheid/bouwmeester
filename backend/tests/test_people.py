"""Tests for people CRUD endpoints."""

import uuid


async def test_list_people(client, sample_person, second_person):
    """GET /api/people returns all people."""
    resp = await client.get("/api/people")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    names = [p["naam"] for p in data]
    assert "Jan Tester" in names
    assert "Piet Tester" in names


async def test_create_person(client):
    """POST /api/people creates a new person."""
    resp = await client.post(
        "/api/people",
        json={
            "naam": "KlaasAnsen",
            "email": "klaas@example.com",
            "functie": "directeur",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["naam"] == "KlaasAnsen"
    assert data["email"] == "klaas@example.com"
    assert data["functie"] == "directeur"
    assert data["is_agent"] is False
    assert "id" in data


async def test_create_agent_duplicate_name_409(client):
    """POST /api/people with duplicate agent name returns 409."""
    agent_payload = {
        "naam": "Bot Agent",
        "email": "bot1@example.com",
        "is_agent": True,
    }
    resp1 = await client.post("/api/people", json=agent_payload)
    assert resp1.status_code == 201

    agent_payload_dup = {
        "naam": "Bot Agent",
        "email": "bot2@example.com",
        "is_agent": True,
    }
    resp2 = await client.post("/api/people", json=agent_payload_dup)
    assert resp2.status_code == 409


async def test_get_person(client, sample_person):
    """GET /api/people/{id} returns the person."""
    resp = await client.get(f"/api/people/{sample_person.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_person.id)
    assert data["naam"] == "Jan Tester"
    assert data["email"] == "jan@example.com"


async def test_get_person_not_found(client):
    """GET /api/people/{id} returns 404 for non-existent person."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/people/{fake_id}")
    assert resp.status_code == 404


async def test_update_person(client, sample_person):
    """PUT /api/people/{id} updates the person."""
    resp = await client.put(
        f"/api/people/{sample_person.id}",
        json={"naam": "Jan Updated", "functie": "manager"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["naam"] == "Jan Updated"
    assert data["functie"] == "manager"
    assert data["email"] == "jan@example.com"


async def test_update_person_not_found(client):
    """PUT /api/people/{id} returns 404 for non-existent person."""
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/people/{fake_id}",
        json={"naam": "Niemand"},
    )
    assert resp.status_code == 404


async def test_delete_person(client, sample_person):
    """DELETE /api/people/{id} removes the person."""
    resp = await client.delete(f"/api/people/{sample_person.id}")
    assert resp.status_code == 204

    # Verify it's gone
    get_resp = await client.get(f"/api/people/{sample_person.id}")
    assert get_resp.status_code == 404


async def test_delete_person_not_found(client):
    """DELETE /api/people/{id} returns 404 for non-existent person."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/people/{fake_id}")
    assert resp.status_code == 404


async def test_list_people_has_emails_phones(client, sample_person):
    """GET /api/people returns eager-loaded emails/phones."""
    resp = await client.get("/api/people")
    assert resp.status_code == 200
    data = resp.json()
    person = next(p for p in data if p["id"] == str(sample_person.id))
    assert len(person["emails"]) == 1
    assert person["emails"][0]["email"] == "jan@example.com"
    assert person["phones"] == []
    assert person["default_email"] == "jan@example.com"


async def test_search_people_with_query(client, sample_person, second_person):
    """GET /api/people/search?q=Jan returns matching people."""
    resp = await client.get("/api/people/search", params={"q": "Jan"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(p["naam"] == "Jan Tester" for p in data)


async def test_search_people_has_emails_phones(client, sample_person):
    """GET /api/people/search returns eager-loaded emails/phones."""
    resp = await client.get("/api/people/search", params={"q": "Jan"})
    assert resp.status_code == 200
    data = resp.json()
    person = next(p for p in data if p["id"] == str(sample_person.id))
    assert len(person["emails"]) == 1
    assert person["emails"][0]["email"] == "jan@example.com"
    assert person["phones"] == []


async def test_search_people_empty_query(client, sample_person, second_person):
    """GET /api/people/search with empty query returns all people."""
    resp = await client.get("/api/people/search", params={"q": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


async def test_get_person_summary(client, sample_person, sample_task):
    """GET /api/people/{id}/summary returns task counts and stakeholder info."""
    resp = await client.get(f"/api/people/{sample_person.id}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["open_task_count"] >= 1
    assert "done_task_count" in data
    assert "open_tasks" in data
    assert "stakeholder_nodes" in data
    assert len(data["open_tasks"]) >= 1
    assert data["open_tasks"][0]["title"] == "Test taak"


async def test_list_org_placements_empty(client, sample_person):
    """GET /api/people/{id}/organisaties returns empty list when no placements."""
    resp = await client.get(f"/api/people/{sample_person.id}/organisaties")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_add_org_placement(client, sample_person, sample_organisatie):
    """POST /api/people/{id}/organisaties creates a placement."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/organisaties",
        json={
            "organisatie_eenheid_id": str(sample_organisatie.id),
            "dienstverband": "in_dienst",
            "start_datum": "2025-01-01",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["person_id"] == str(sample_person.id)
    assert data["organisatie_eenheid_id"] == str(sample_organisatie.id)
    assert data["organisatie_eenheid_naam"] == "Test Ministerie"
    assert data["dienstverband"] == "in_dienst"
    assert data["start_datum"] == "2025-01-01"
    assert data["eind_datum"] is None

    # Verify it shows up in the list
    list_resp = await client.get(f"/api/people/{sample_person.id}/organisaties")
    assert len(list_resp.json()) == 1


async def test_add_org_placement_duplicate_active_409(
    client, sample_person, sample_organisatie
):
    """POST /api/people/{id}/organisaties returns 409 for duplicate active placement."""
    payload = {
        "organisatie_eenheid_id": str(sample_organisatie.id),
        "dienstverband": "in_dienst",
        "start_datum": "2025-01-01",
    }
    resp1 = await client.post(
        f"/api/people/{sample_person.id}/organisaties",
        json=payload,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/people/{sample_person.id}/organisaties",
        json=payload,
    )
    assert resp2.status_code == 409


async def test_delete_org_placement(client, sample_person, sample_organisatie):
    """DELETE /api/people/{id}/organisaties/{placement_id} removes the placement."""
    create_resp = await client.post(
        f"/api/people/{sample_person.id}/organisaties",
        json={
            "organisatie_eenheid_id": str(sample_organisatie.id),
            "dienstverband": "extern",
            "start_datum": "2025-06-01",
        },
    )
    assert create_resp.status_code == 201
    placement_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/people/{sample_person.id}/organisaties/{placement_id}"
    )
    assert del_resp.status_code == 204

    # Verify it's gone
    list_resp = await client.get(f"/api/people/{sample_person.id}/organisaties")
    assert len(list_resp.json()) == 0
