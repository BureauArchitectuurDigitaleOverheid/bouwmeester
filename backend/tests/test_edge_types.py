"""Comprehensive API tests for the edge_types router."""


# ---------------------------------------------------------------------------
# List edge types
# ---------------------------------------------------------------------------


async def test_list_edge_types_returns_200(client):
    """GET /api/edge-types returns 200 and a list."""
    resp = await client.get("/api/edge-types")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_edge_types_includes_fixture(client, sample_edge_type):
    """GET /api/edge-types includes the fixture edge type."""
    resp = await client.get("/api/edge-types")
    assert resp.status_code == 200
    data = resp.json()
    ids = {et["id"] for et in data}
    assert sample_edge_type.id in ids


# ---------------------------------------------------------------------------
# Create edge type
# ---------------------------------------------------------------------------


async def test_create_edge_type(client):
    """POST /api/edge-types creates an edge type and returns 201."""
    payload = {
        "id": "nieuw_type",
        "label_nl": "Nieuw type",
        "label_en": "New type",
        "description": "Een nieuw relatietype",
    }
    resp = await client.post("/api/edge-types", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "nieuw_type"
    assert data["label_nl"] == "Nieuw type"
    assert data["label_en"] == "New type"
    assert data["description"] == "Een nieuw relatietype"
    assert data["is_custom"] is False


# ---------------------------------------------------------------------------
# Get edge type by ID
# ---------------------------------------------------------------------------


async def test_get_edge_type(client, sample_edge_type):
    """GET /api/edge-types/{id} returns the edge type."""
    resp = await client.get(f"/api/edge-types/{sample_edge_type.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_edge_type.id
    assert data["label_nl"] == "Test relatie"
    assert data["label_en"] == "Test relation"
    assert data["description"] == "Een test relatie"
    assert data["is_custom"] is True


async def test_get_edge_type_not_found(client):
    """GET /api/edge-types/{id} returns 404 for non-existent edge type."""
    resp = await client.get("/api/edge-types/does_not_exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete edge type
# ---------------------------------------------------------------------------


async def test_delete_edge_type(client, sample_edge_type):
    """DELETE /api/edge-types/{id} removes the edge type and returns 204."""
    resp = await client.delete(f"/api/edge-types/{sample_edge_type.id}")
    assert resp.status_code == 204

    # Verify it is gone
    get_resp = await client.get(f"/api/edge-types/{sample_edge_type.id}")
    assert get_resp.status_code == 404


async def test_delete_edge_type_not_found(client):
    """DELETE /api/edge-types/{id} returns 404 for non-existent edge type."""
    resp = await client.delete("/api/edge-types/does_not_exist")
    assert resp.status_code == 404
