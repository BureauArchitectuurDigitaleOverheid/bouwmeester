"""Comprehensive API tests for the edges router."""

import uuid

# ---------------------------------------------------------------------------
# List edges
# ---------------------------------------------------------------------------


async def test_list_edges_returns_200(client):
    """GET /api/edges returns 200 and a list."""
    resp = await client.get("/api/edges")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_edges_includes_fixture_edge(client, sample_edge):
    """GET /api/edges includes the fixture edge in the result."""
    resp = await client.get("/api/edges")
    assert resp.status_code == 200
    data = resp.json()
    ids = {e["id"] for e in data}
    assert str(sample_edge.id) in ids


async def test_list_edges_filtered_by_from_node_id(
    client, sample_edge, sample_node, second_node
):
    """GET /api/edges?from_node_id=... returns only edges originating from that node."""
    resp = await client.get("/api/edges", params={"from_node_id": str(sample_node.id)})
    assert resp.status_code == 200
    data = resp.json()
    # All returned edges must have from_node_id matching the filter
    assert all(e["from_node_id"] == str(sample_node.id) for e in data)
    # Our fixture edge should be present
    ids = {e["id"] for e in data}
    assert str(sample_edge.id) in ids


async def test_list_edges_filtered_by_to_node_id(
    client, sample_edge, sample_node, second_node
):
    """GET /api/edges?to_node_id=... returns only edges pointing to that node."""
    resp = await client.get("/api/edges", params={"to_node_id": str(second_node.id)})
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["to_node_id"] == str(second_node.id) for e in data)
    ids = {e["id"] for e in data}
    assert str(sample_edge.id) in ids


async def test_list_edges_filtered_by_node_id(
    client, sample_edge, sample_node, second_node
):
    """GET /api/edges?node_id=... returns edges where the node is either from or to."""
    # Filter by sample_node (from side)
    resp = await client.get("/api/edges", params={"node_id": str(sample_node.id)})
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert str(sample_edge.id) in ids

    # Filter by second_node (to side) should also find it
    resp2 = await client.get("/api/edges", params={"node_id": str(second_node.id)})
    assert resp2.status_code == 200
    ids2 = {e["id"] for e in resp2.json()}
    assert str(sample_edge.id) in ids2


# ---------------------------------------------------------------------------
# Create edge
# ---------------------------------------------------------------------------


async def test_create_edge(client, sample_node, second_node, sample_edge_type):
    """POST /api/edges creates an edge and returns 201."""
    payload = {
        "from_node_id": str(sample_node.id),
        "to_node_id": str(second_node.id),
        "edge_type_id": sample_edge_type.id,
        "weight": 2.5,
        "description": "Nieuwe relatie",
    }
    resp = await client.post("/api/edges", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["from_node_id"] == str(sample_node.id)
    assert data["to_node_id"] == str(second_node.id)
    assert data["edge_type_id"] == sample_edge_type.id
    assert data["weight"] == 2.5
    assert data["description"] == "Nieuwe relatie"
    assert "id" in data
    assert "created_at" in data


# ---------------------------------------------------------------------------
# Get edge by ID
# ---------------------------------------------------------------------------


async def test_get_edge_by_id(client, sample_edge, sample_node, second_node):
    """GET /api/edges/{id} returns the edge with from_node and to_node."""
    resp = await client.get(f"/api/edges/{sample_edge.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_edge.id)
    assert data["from_node_id"] == str(sample_node.id)
    assert data["to_node_id"] == str(second_node.id)
    assert data["description"] == "Test edge"
    # EdgeWithNodes includes nested node objects
    assert "from_node" in data
    assert data["from_node"]["id"] == str(sample_node.id)
    assert data["from_node"]["title"] == "Test dossier"
    assert "to_node" in data
    assert data["to_node"]["id"] == str(second_node.id)
    assert data["to_node"]["title"] == "Test doel"


async def test_get_edge_not_found(client):
    """GET /api/edges/{id} returns 404 for a non-existent edge."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/edges/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update edge
# ---------------------------------------------------------------------------


async def test_update_edge_weight(client, sample_edge):
    """PUT /api/edges/{id} updates the edge weight."""
    payload = {"weight": 5.0}
    resp = await client.put(f"/api/edges/{sample_edge.id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["weight"] == 5.0
    # Other fields remain unchanged
    assert data["description"] == "Test edge"
    assert data["edge_type_id"] == "test_relatie"


async def test_update_edge_description(client, sample_edge):
    """PUT /api/edges/{id} updates the edge description."""
    payload = {"description": "Bijgewerkte beschrijving"}
    resp = await client.put(f"/api/edges/{sample_edge.id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Bijgewerkte beschrijving"
    assert data["weight"] == 1.0  # unchanged


async def test_update_edge_not_found(client):
    """PUT /api/edges/{id} returns 404 for a non-existent edge."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/edges/{fake_id}", json={"weight": 3.0})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete edge
# ---------------------------------------------------------------------------


async def test_delete_edge(client, sample_edge):
    """DELETE /api/edges/{id} removes the edge and returns 204."""
    resp = await client.delete(f"/api/edges/{sample_edge.id}")
    assert resp.status_code == 204

    # Verify it is gone
    get_resp = await client.get(f"/api/edges/{sample_edge.id}")
    assert get_resp.status_code == 404


async def test_delete_edge_not_found(client):
    """DELETE /api/edges/{id} returns 404 for a non-existent edge."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/edges/{fake_id}")
    assert resp.status_code == 404
