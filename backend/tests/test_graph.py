"""Comprehensive API tests for the graph router."""

import uuid

from bouwmeester.models.corpus_node import CorpusNode

# ---------------------------------------------------------------------------
# Graph search
# ---------------------------------------------------------------------------


async def test_graph_search_returns_200(client):
    """GET /api/graph/search returns 200 and a graph view."""
    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


async def test_graph_search_with_data(client, sample_node, sample_edge):
    """GET /api/graph/search returns nodes and edges when data exists."""
    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert str(sample_node.id) in node_ids
    edge_ids = {e["id"] for e in data["edges"]}
    assert str(sample_edge.id) in edge_ids


async def test_graph_search_filter_by_node_type(client, sample_node):
    """GET /api/graph/search?node_types=dossier filters by node type."""
    resp = await client.get("/api/graph/search", params={"node_types": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    for n in data["nodes"]:
        assert n["node_type"] == "dossier"


async def test_graph_search_with_long_title(client, db_session):
    """Nodes with titles > 500 chars must not crash graph/search (regression #107)."""
    long_title = "A" * 719  # reproduces parlementaire import with long onderwerp
    node = CorpusNode(
        id=uuid.uuid4(),
        title=long_title,
        node_type="politieke_input",
        description="Test node with long title",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    resp = await client.get("/api/graph/search")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert str(node.id) in node_ids
    # The long title must be returned in full
    matched = [n for n in data["nodes"] if n["id"] == str(node.id)]
    assert matched[0]["title"] == long_title


async def test_list_nodes_with_long_title(client, db_session):
    """Nodes list must not 500 on titles > 500 chars (regression #107)."""
    long_title = "B" * 600
    node = CorpusNode(
        id=uuid.uuid4(),
        title=long_title,
        node_type="politieke_input",
        description="Test node with long title",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    resp = await client.get("/api/nodes", params={"node_type": "politieke_input"})
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data}
    assert str(node.id) in node_ids


# ---------------------------------------------------------------------------
# Find path
# ---------------------------------------------------------------------------


async def test_find_path_returns_200(client, sample_node, second_node, sample_edge):
    """GET /api/graph/path?from_id=...&to_id=... returns a path result."""
    resp = await client.get(
        "/api/graph/path",
        params={
            "from_id": str(sample_node.id),
            "to_id": str(second_node.id),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "from_id" in data
    assert "to_id" in data
    assert "path" in data
    assert "length" in data
    assert data["from_id"] == str(sample_node.id)
    assert data["to_id"] == str(second_node.id)
