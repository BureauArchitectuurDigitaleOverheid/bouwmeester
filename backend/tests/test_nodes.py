"""Comprehensive API tests for the corpus nodes router."""

import uuid


# ---------------------------------------------------------------------------
# List nodes
# ---------------------------------------------------------------------------


async def test_list_nodes_returns_200(client):
    """GET /api/nodes returns 200 and a list."""
    resp = await client.get("/api/nodes")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_nodes_includes_created(client, sample_node, second_node):
    """GET /api/nodes includes fixture nodes in the result."""
    resp = await client.get("/api/nodes")
    assert resp.status_code == 200
    data = resp.json()
    ids = {n["id"] for n in data}
    assert str(sample_node.id) in ids
    assert str(second_node.id) in ids


async def test_list_nodes_filtered_by_type(client, sample_node, second_node):
    """GET /api/nodes?node_type=dossier returns only dossier-type nodes."""
    resp = await client.get("/api/nodes", params={"node_type": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(n["node_type"] == "dossier" for n in data)
    ids = {n["id"] for n in data}
    assert str(sample_node.id) in ids
    # second_node is a doel, so it should not appear
    assert str(second_node.id) not in ids


# ---------------------------------------------------------------------------
# Create node
# ---------------------------------------------------------------------------


async def test_create_node(client):
    """POST /api/nodes creates a node and returns 201."""
    payload = {
        "title": "Nieuw beleidskader",
        "description": "Omschrijving",
        "node_type": "beleidskader",
        "status": "concept",
    }
    resp = await client.post("/api/nodes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Nieuw beleidskader"
    assert data["description"] == "Omschrijving"
    assert data["node_type"] == "beleidskader"
    assert data["status"] == "concept"
    assert "id" in data
    assert "created_at" in data


async def test_create_node_invalid_data(client):
    """POST /api/nodes with missing required fields returns 422."""
    resp = await client.post("/api/nodes", json={"description": "Geen titel"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get node by ID
# ---------------------------------------------------------------------------


async def test_get_node(client, sample_node):
    """GET /api/nodes/{id} returns the node with edge lists."""
    resp = await client.get(f"/api/nodes/{sample_node.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test dossier"
    assert data["node_type"] == "dossier"
    assert data["description"] == "Testomschrijving"
    assert data["status"] == "actief"
    assert "edges_from" in data
    assert "edges_to" in data
    assert data["edge_count"] == 0


async def test_get_node_not_found(client):
    """GET /api/nodes/{id} returns 404 for non-existent node."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/nodes/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update node
# ---------------------------------------------------------------------------


async def test_update_node(client, sample_node):
    """PUT /api/nodes/{id} updates the node fields."""
    payload = {"title": "Gewijzigd dossier", "status": "inactief"}
    resp = await client.put(f"/api/nodes/{sample_node.id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Gewijzigd dossier"
    assert data["status"] == "inactief"
    # node_type should remain unchanged
    assert data["node_type"] == "dossier"


async def test_update_node_not_found(client):
    """PUT /api/nodes/{id} returns 404 for non-existent node."""
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/nodes/{fake_id}",
        json={"title": "Bestaat niet"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete node
# ---------------------------------------------------------------------------


async def test_delete_node(client, sample_node):
    """DELETE /api/nodes/{id} removes the node and returns 204."""
    resp = await client.delete(f"/api/nodes/{sample_node.id}")
    assert resp.status_code == 204

    # Verify it is gone
    get_resp = await client.get(f"/api/nodes/{sample_node.id}")
    assert get_resp.status_code == 404


async def test_delete_node_not_found(client):
    """DELETE /api/nodes/{id} returns 404 for non-existent node."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/nodes/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Neighbors
# ---------------------------------------------------------------------------


async def test_get_neighbors(client, sample_node, second_node, sample_edge):
    """GET /api/nodes/{id}/neighbors returns neighbor nodes and edges."""
    resp = await client.get(f"/api/nodes/{sample_node.id}/neighbors")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node"]["id"] == str(sample_node.id)
    assert len(data["neighbors"]) == 1
    neighbor = data["neighbors"][0]
    assert neighbor["node"]["id"] == str(second_node.id)
    assert "edge" in neighbor


async def test_get_neighbors_not_found(client):
    """GET /api/nodes/{id}/neighbors returns 404 for non-existent node."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/nodes/{fake_id}/neighbors")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


async def test_get_node_tasks(client, sample_node, sample_task):
    """GET /api/nodes/{id}/tasks returns tasks linked to the node."""
    resp = await client.get(f"/api/nodes/{sample_node.id}/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test taak"


async def test_get_node_tasks_empty(client, sample_node):
    """GET /api/nodes/{id}/tasks returns empty list when no tasks exist."""
    resp = await client.get(f"/api/nodes/{sample_node.id}/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


async def test_get_node_tags_empty(client, sample_node):
    """GET /api/nodes/{id}/tags returns empty list when no tags attached."""
    resp = await client.get(f"/api/nodes/{sample_node.id}/tags")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_add_tag_by_id(client, sample_node, sample_tag):
    """POST /api/nodes/{id}/tags with tag_id attaches existing tag."""
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/tags",
        json={"tag_id": str(sample_tag.id)},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["tag"]["id"] == str(sample_tag.id)
    assert data["tag"]["name"] == "Test tag"

    # Verify via GET
    list_resp = await client.get(f"/api/nodes/{sample_node.id}/tags")
    assert len(list_resp.json()) == 1


async def test_add_tag_by_name_creates_new(client, sample_node):
    """POST /api/nodes/{id}/tags with tag_name creates a new tag and attaches it."""
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/tags",
        json={"tag_name": "Gloednieuw label"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["tag"]["name"] == "Gloednieuw label"


async def test_get_node_tags_with_tag(client, sample_node, sample_tag):
    """GET /api/nodes/{id}/tags returns attached tags."""
    await client.post(
        f"/api/nodes/{sample_node.id}/tags",
        json={"tag_id": str(sample_tag.id)},
    )
    resp = await client.get(f"/api/nodes/{sample_node.id}/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tag"]["name"] == "Test tag"


async def test_remove_tag_from_node(client, sample_node, sample_tag):
    """DELETE /api/nodes/{id}/tags/{tag_id} removes the tag link and returns 204."""
    await client.post(
        f"/api/nodes/{sample_node.id}/tags",
        json={"tag_id": str(sample_tag.id)},
    )
    resp = await client.delete(
        f"/api/nodes/{sample_node.id}/tags/{sample_tag.id}",
    )
    assert resp.status_code == 204

    # Verify it is gone
    list_resp = await client.get(f"/api/nodes/{sample_node.id}/tags")
    assert list_resp.json() == []


async def test_remove_tag_not_found(client, sample_node):
    """DELETE /api/nodes/{id}/tags/{tag_id} returns 404 for non-existent link."""
    fake_tag_id = uuid.uuid4()
    resp = await client.delete(
        f"/api/nodes/{sample_node.id}/tags/{fake_tag_id}",
    )
    assert resp.status_code == 404
