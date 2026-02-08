"""Comprehensive API tests for the tags router."""

import uuid


# ---------------------------------------------------------------------------
# List tags
# ---------------------------------------------------------------------------


async def test_list_tags_returns_200(client):
    """GET /api/tags returns 200 and a list."""
    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_tags_includes_fixture_tag(client, sample_tag):
    """GET /api/tags includes the fixture tag in the result."""
    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    ids = {t["id"] for t in data}
    assert str(sample_tag.id) in ids


# ---------------------------------------------------------------------------
# Tag tree
# ---------------------------------------------------------------------------


async def test_get_tag_tree_returns_200(client):
    """GET /api/tags/tree returns 200 and a list of tree nodes."""
    resp = await client.get("/api/tags/tree")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Search tags
# ---------------------------------------------------------------------------


async def test_search_tags_by_name(client, sample_tag):
    """GET /api/tags/search?q=Test finds the fixture tag."""
    resp = await client.get("/api/tags/search", params={"q": "Test tag"})
    assert resp.status_code == 200
    data = resp.json()
    ids = {t["id"] for t in data}
    assert str(sample_tag.id) in ids


async def test_search_tags_no_match(client):
    """GET /api/tags/search?q=... returns empty list when nothing matches."""
    resp = await client.get(
        "/api/tags/search", params={"q": "xyznonexistent999"}
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Create tag
# ---------------------------------------------------------------------------


async def test_create_tag(client):
    """POST /api/tags creates a tag and returns 201."""
    payload = {"name": "Nieuwe tag", "description": "Beschrijving"}
    resp = await client.post("/api/tags", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Nieuwe tag"
    assert data["description"] == "Beschrijving"
    assert "id" in data
    assert "created_at" in data


# ---------------------------------------------------------------------------
# Get tag by ID
# ---------------------------------------------------------------------------


async def test_get_tag_by_id(client, sample_tag):
    """GET /api/tags/{id} returns the tag."""
    resp = await client.get(f"/api/tags/{sample_tag.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_tag.id)
    assert data["name"] == "Test tag"
    assert data["description"] == "Een test tag"


async def test_get_tag_not_found(client):
    """GET /api/tags/{id} returns 404 for non-existent tag."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/tags/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update tag
# ---------------------------------------------------------------------------


async def test_update_tag_name(client, sample_tag):
    """PUT /api/tags/{id} updates the tag name."""
    payload = {"name": "Gewijzigde tag"}
    resp = await client.put(f"/api/tags/{sample_tag.id}", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Gewijzigde tag"
    # Description should remain unchanged
    assert data["description"] == "Een test tag"


# ---------------------------------------------------------------------------
# Delete tag
# ---------------------------------------------------------------------------


async def test_delete_tag(client, sample_tag):
    """DELETE /api/tags/{id} removes the tag and returns 204."""
    resp = await client.delete(f"/api/tags/{sample_tag.id}")
    assert resp.status_code == 204

    # Verify it is gone
    get_resp = await client.get(f"/api/tags/{sample_tag.id}")
    assert get_resp.status_code == 404
