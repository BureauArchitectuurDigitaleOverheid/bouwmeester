"""Comprehensive API tests for the import_export router."""


# ---------------------------------------------------------------------------
# Export nodes
# ---------------------------------------------------------------------------


async def test_export_nodes_csv(client, sample_node):
    """GET /api/export/nodes returns CSV content."""
    resp = await client.get("/api/export/nodes")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    text = resp.text
    # CSV should have header row and at least one data row
    lines = text.strip().split("\n")
    assert len(lines) >= 2


async def test_export_nodes_csv_filter_by_type(client, sample_node):
    """GET /api/export/nodes?node_type=dossier filters by type."""
    resp = await client.get("/api/export/nodes", params={"node_type": "dossier"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Export edges
# ---------------------------------------------------------------------------


async def test_export_edges_csv(client, sample_edge):
    """GET /api/export/edges returns CSV content."""
    resp = await client.get("/api/export/edges")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Export corpus JSON
# ---------------------------------------------------------------------------


async def test_export_corpus_json(client, sample_node, sample_edge):
    """GET /api/export/corpus returns JSON with nodes and edges."""
    resp = await client.get("/api/export/corpus")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "edge_types" in data


# ---------------------------------------------------------------------------
# Export ArchiMate
# ---------------------------------------------------------------------------


async def test_export_archimate_xml(client, sample_node):
    """GET /api/export/archimate returns XML content."""
    resp = await client.get("/api/export/archimate")
    assert resp.status_code == 200
    assert "xml" in resp.headers.get("content-type", "")
    # Should be valid XML starting with declaration or root element
    assert resp.text.startswith("<?xml") or resp.text.startswith("<")
