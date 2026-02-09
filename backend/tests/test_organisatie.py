"""Comprehensive API tests for the organisatie router."""

import uuid
from datetime import date

from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

# ---------------------------------------------------------------------------
# List organisatie
# ---------------------------------------------------------------------------


async def test_list_organisatie_flat_returns_200(client):
    """GET /api/organisatie returns 200 and a list in flat format."""
    resp = await client.get("/api/organisatie")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_organisatie_flat_includes_created(client, sample_organisatie):
    """GET /api/organisatie (flat) includes the fixture org unit."""
    resp = await client.get("/api/organisatie", params={"format": "flat"})
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert str(sample_organisatie.id) in ids


async def test_list_organisatie_tree_format(
    client, sample_organisatie, child_organisatie
):
    """GET /api/organisatie?format=tree returns a tree structure with children."""
    resp = await client.get("/api/organisatie", params={"format": "tree"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Find the root node for our test ministerie
    test_root = None
    for node in data:
        if node["id"] == str(sample_organisatie.id):
            test_root = node
            break
    assert test_root is not None, "Test ministerie should appear as root node"
    assert "children" in test_root
    child_ids = {c["id"] for c in test_root["children"]}
    assert str(child_organisatie.id) in child_ids


# ---------------------------------------------------------------------------
# Search organisatie
# ---------------------------------------------------------------------------


async def test_search_organisatie(client, sample_organisatie):
    """GET /api/organisatie/search?q=... returns matching org units."""
    resp = await client.get("/api/organisatie/search", params={"q": "Test Ministerie"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    ids = {item["id"] for item in data}
    assert str(sample_organisatie.id) in ids


async def test_search_organisatie_empty_query_returns_empty(client):
    """GET /api/organisatie/search?q= with empty query returns empty list."""
    resp = await client.get("/api/organisatie/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Create organisatie
# ---------------------------------------------------------------------------


async def test_create_organisatie(client):
    """POST /api/organisatie creates a new org unit and returns 201."""
    payload = {
        "naam": "Nieuwe Directie",
        "type": "directie",
        "beschrijving": "Een nieuwe directie",
    }
    resp = await client.post("/api/organisatie", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["naam"] == "Nieuwe Directie"
    assert data["type"] == "directie"
    assert data["beschrijving"] == "Een nieuwe directie"
    assert "id" in data
    assert "created_at" in data


async def test_create_organisatie_with_parent(client, sample_organisatie):
    """POST /api/organisatie with parent_id creates a child unit."""
    payload = {
        "naam": "Sub-afdeling",
        "type": "afdeling",
        "parent_id": str(sample_organisatie.id),
    }
    resp = await client.post("/api/organisatie", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["parent_id"] == str(sample_organisatie.id)


# ---------------------------------------------------------------------------
# Get organisatie by ID
# ---------------------------------------------------------------------------


async def test_get_organisatie_by_id(client, sample_organisatie):
    """GET /api/organisatie/{id} returns the org unit."""
    resp = await client.get(f"/api/organisatie/{sample_organisatie.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_organisatie.id)
    assert data["naam"] == "Test Ministerie"
    assert data["type"] == "ministerie"
    assert data["beschrijving"] == "Een test ministerie"


async def test_get_organisatie_not_found(client):
    """GET /api/organisatie/{id} returns 404 for a non-existent org unit."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/organisatie/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update organisatie
# ---------------------------------------------------------------------------


async def test_update_organisatie(client, sample_organisatie):
    """PUT /api/organisatie/{id} updates the org unit fields."""
    payload = {"naam": "Gewijzigd Ministerie", "beschrijving": "Bijgewerkt"}
    resp = await client.put(f"/api/organisatie/{sample_organisatie.id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["naam"] == "Gewijzigd Ministerie"
    assert data["beschrijving"] == "Bijgewerkt"
    # type should remain unchanged
    assert data["type"] == "ministerie"


# ---------------------------------------------------------------------------
# Delete organisatie
# ---------------------------------------------------------------------------


async def test_delete_organisatie_without_children(client, sample_organisatie):
    """DELETE /api/organisatie/{id} removes a childless org unit and returns 204."""
    resp = await client.delete(f"/api/organisatie/{sample_organisatie.id}")
    assert resp.status_code == 204

    # Verify it is gone
    get_resp = await client.get(f"/api/organisatie/{sample_organisatie.id}")
    assert get_resp.status_code == 404


async def test_delete_organisatie_with_children_fails(
    client, sample_organisatie, child_organisatie
):
    """DELETE /api/organisatie/{id} returns 409 if org unit has children."""
    resp = await client.delete(f"/api/organisatie/{sample_organisatie.id}")
    assert resp.status_code == 409
    assert "subeenheden" in resp.json()["detail"]


async def test_delete_organisatie_with_personen_fails(
    client, db_session, sample_organisatie, sample_person
):
    """DELETE /api/organisatie/{id} returns 409 if org unit has active personen."""
    # Link person to org unit via the junction table
    link = PersonOrganisatieEenheid(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        organisatie_eenheid_id=sample_organisatie.id,
        dienstverband="in_dienst",
        start_datum=date(2024, 1, 1),
        eind_datum=None,
    )
    db_session.add(link)
    await db_session.flush()

    resp = await client.delete(f"/api/organisatie/{sample_organisatie.id}")
    assert resp.status_code == 409
    assert "personen" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Managed-by
# ---------------------------------------------------------------------------


async def test_managed_by_with_manager(
    client, db_session, sample_organisatie, sample_person
):
    """GET /api/organisatie/managed-by/{person_id} returns units managed by person."""
    from datetime import date

    from bouwmeester.models.org_manager import OrganisatieEenheidManager

    # Set sample_person as manager (legacy column + temporal record)
    sample_organisatie.manager_id = sample_person.id
    db_session.add(sample_organisatie)
    db_session.add(
        OrganisatieEenheidManager(
            eenheid_id=sample_organisatie.id,
            manager_id=sample_person.id,
            geldig_van=date.today(),
        )
    )
    await db_session.flush()

    resp = await client.get(f"/api/organisatie/managed-by/{sample_person.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    ids = {item["id"] for item in data}
    assert str(sample_organisatie.id) in ids


async def test_managed_by_without_data(client):
    """Managed-by returns empty list for non-manager."""
    fake_person_id = uuid.uuid4()
    resp = await client.get(f"/api/organisatie/managed-by/{fake_person_id}")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Personen for organisatie
# ---------------------------------------------------------------------------


async def test_get_personen_for_organisatie(
    client, db_session, sample_organisatie, sample_person
):
    """GET /api/organisatie/{id}/personen returns people linked to the org unit."""
    # Link person to org unit via the junction table
    link = PersonOrganisatieEenheid(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        organisatie_eenheid_id=sample_organisatie.id,
        dienstverband="in_dienst",
        start_datum=date(2024, 1, 1),
        eind_datum=None,
    )
    db_session.add(link)
    await db_session.flush()

    resp = await client.get(f"/api/organisatie/{sample_organisatie.id}/personen")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    names = {p["naam"] for p in data}
    assert "Jan Tester" in names


async def test_get_personen_for_organisatie_empty(client, sample_organisatie):
    """GET /api/organisatie/{id}/personen returns empty when no people linked."""
    resp = await client.get(f"/api/organisatie/{sample_organisatie.id}/personen")
    assert resp.status_code == 200
    assert resp.json() == []
