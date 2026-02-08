"""Comprehensive API tests for the mentions router."""

import uuid

# ---------------------------------------------------------------------------
# Search mentionables
# ---------------------------------------------------------------------------


async def test_search_mentionables_returns_200(client, sample_node):
    """GET /api/mentions/search?q=... returns 200 and a list."""
    resp = await client.get("/api/mentions/search", params={"q": "Test"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_search_mentionables_empty_query(client):
    """GET /api/mentions/search?q= returns empty list for empty query."""
    resp = await client.get("/api/mentions/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_mentionables_finds_node(client, sample_node):
    """GET /api/mentions/search?q=dossier finds the test node."""
    resp = await client.get(
        "/api/mentions/search", params={"q": "dossier", "types": "node"}
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data}
    assert str(sample_node.id) in ids


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------


async def test_get_references_returns_200(client, sample_node):
    """GET /api/mentions/references/{target_id} returns 200 and a list."""
    resp = await client.get(f"/api/mentions/references/{sample_node.id}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_references_unknown_target(client):
    """References returns empty list for unknown target."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/mentions/references/{fake_id}")
    assert resp.status_code == 200
    assert resp.json() == []
