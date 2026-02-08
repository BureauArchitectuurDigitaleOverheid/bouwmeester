"""Comprehensive API tests for the search router."""


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


async def test_search_returns_200(client, sample_node):
    """GET /api/search?q=... returns 200 and a SearchResponse."""
    resp = await client.get("/api/search", params={"q": "Test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "total" in data
    assert "query" in data
    assert data["query"] == "Test"


async def test_search_finds_node(client, sample_node):
    """GET /api/search?q=dossier finds the test dossier node."""
    resp = await client.get("/api/search", params={"q": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert str(sample_node.id) in ids


async def test_search_no_match(client):
    """GET /api/search?q=... returns empty results when nothing matches."""
    resp = await client.get("/api/search", params={"q": "xyznonexistent999"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


async def test_search_filter_by_node_type(client, sample_node):
    """GET /api/search?q=...&node_types=dossier filters by node type."""
    resp = await client.get(
        "/api/search", params={"q": "Test", "node_types": "dossier"}
    )
    assert resp.status_code == 200
    data = resp.json()
    # All results should be of type dossier
    for r in data["results"]:
        assert r["node_type"] == "dossier"
