"""Comprehensive API tests for the parlementair router."""

import uuid
from datetime import date

# ---------------------------------------------------------------------------
# Fixtures (local to parlementair tests)
# ---------------------------------------------------------------------------


async def _create_parlementair_item(db_session, corpus_node_id=None, status="pending"):
    """Helper to create a ParlementairItem record."""
    from bouwmeester.models.parlementair_item import ParlementairItem

    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-42",
        titel="Test motie",
        onderwerp="Test onderwerp",
        bron="tweede_kamer",
        datum=date(2024, 6, 15),
        status=status,
        corpus_node_id=corpus_node_id,
    )
    db_session.add(item)
    await db_session.flush()
    return item


async def _create_suggested_edge(
    db_session, parlementair_item_id, target_node_id, edge_type_id
):
    """Helper to create a SuggestedEdge record."""
    from bouwmeester.models.parlementair_item import SuggestedEdge

    se = SuggestedEdge(
        id=uuid.uuid4(),
        parlementair_item_id=parlementair_item_id,
        target_node_id=target_node_id,
        edge_type_id=edge_type_id,
        confidence=0.85,
        reason="Automatisch gevonden",
        status="pending",
    )
    db_session.add(se)
    await db_session.flush()
    return se


# ---------------------------------------------------------------------------
# List imports
# ---------------------------------------------------------------------------


async def test_list_imports_returns_200(client):
    """GET /api/parlementair/imports returns 200 and a list."""
    resp = await client.get("/api/parlementair/imports")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_imports_includes_fixture(client, db_session):
    """GET /api/parlementair/imports includes a created import."""
    item = await _create_parlementair_item(db_session)
    resp = await client.get("/api/parlementair/imports")
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()}
    assert str(item.id) in ids


async def test_list_imports_filter_by_status(client, db_session):
    """GET /api/parlementair/imports?status=pending filters by status."""
    await _create_parlementair_item(db_session, status="pending")
    resp = await client.get("/api/parlementair/imports", params={"status": "pending"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(m["status"] == "pending" for m in data)


# ---------------------------------------------------------------------------
# Get import by ID
# ---------------------------------------------------------------------------


async def test_get_import_by_id(client, db_session):
    """GET /api/parlementair/imports/{id} returns the import."""
    item = await _create_parlementair_item(db_session)
    resp = await client.get(f"/api/parlementair/imports/{item.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(item.id)
    assert data["titel"] == "Test motie"
    assert data["type"] == "motie"


async def test_get_import_not_found(client):
    """GET /api/parlementair/imports/{id} returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/parlementair/imports/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------


async def test_review_queue_returns_200(client):
    """GET /api/parlementair/review-queue returns 200 and a list."""
    resp = await client.get("/api/parlementair/review-queue")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Reject import
# ---------------------------------------------------------------------------


async def test_reject_import(client, db_session):
    """PUT /api/parlementair/imports/{id}/reject changes status to rejected."""
    item = await _create_parlementair_item(db_session, status="imported")
    resp = await client.put(f"/api/parlementair/imports/{item.id}/reject")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["reviewed_at"] is not None


async def test_reject_import_not_found(client):
    """PUT /api/parlementair/imports/{id}/reject returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/parlementair/imports/{fake_id}/reject")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Complete review
# ---------------------------------------------------------------------------


async def test_complete_review(client, db_session, sample_node, sample_person):
    """POST /api/parlementair/imports/{id}/complete sets status to reviewed."""
    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    payload = {
        "eigenaar_id": str(sample_person.id),
        "tasks": [],
    }
    resp = await client.post(
        f"/api/parlementair/imports/{item.id}/complete", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "reviewed"


async def test_complete_review_not_found(client, sample_person):
    """POST /api/parlementair/imports/{id}/complete returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    payload = {"eigenaar_id": str(sample_person.id), "tasks": []}
    resp = await client.post(
        f"/api/parlementair/imports/{fake_id}/complete", json=payload
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Approve suggested edge
# ---------------------------------------------------------------------------


async def test_approve_edge(
    client, db_session, sample_node, second_node, sample_edge_type
):
    """PUT /api/parlementair/edges/{id}/approve creates an actual edge."""
    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    se = await _create_suggested_edge(
        db_session, item.id, second_node.id, sample_edge_type.id
    )
    resp = await client.put(f"/api/parlementair/edges/{se.id}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["edge_id"] is not None


async def test_approve_edge_not_found(client):
    """PUT /api/parlementair/edges/{id}/approve returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/parlementair/edges/{fake_id}/approve")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reject suggested edge
# ---------------------------------------------------------------------------


async def test_reject_edge(
    client, db_session, sample_node, second_node, sample_edge_type
):
    """PUT /api/parlementair/edges/{id}/reject marks edge as rejected."""
    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    se = await _create_suggested_edge(
        db_session, item.id, second_node.id, sample_edge_type.id
    )
    resp = await client.put(f"/api/parlementair/edges/{se.id}/reject")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"


async def test_reject_edge_not_found(client):
    """PUT /api/parlementair/edges/{id}/reject returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/parlementair/edges/{fake_id}/reject")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update suggested edge type
# ---------------------------------------------------------------------------


async def test_update_suggested_edge_type(
    client, db_session, sample_node, second_node, sample_edge_type
):
    """PATCH /api/parlementair/edges/{id} changes the edge_type_id."""
    from bouwmeester.models.edge_type import EdgeType

    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    se = await _create_suggested_edge(
        db_session, item.id, second_node.id, sample_edge_type.id
    )
    # Create a second edge type to switch to
    et2 = EdgeType(
        id="andere_relatie",
        label_nl="Andere relatie",
        label_en="Other relation",
        description="Een andere relatie",
        is_custom=True,
    )
    db_session.add(et2)
    await db_session.flush()

    resp = await client.patch(
        f"/api/parlementair/edges/{se.id}",
        json={"edge_type_id": "andere_relatie"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["edge_type_id"] == "andere_relatie"
    assert data["status"] == "pending"


async def test_update_suggested_edge_not_found(client):
    """PATCH /api/parlementair/edges/{id} returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/parlementair/edges/{fake_id}",
        json={"edge_type_id": "some_type"},
    )
    assert resp.status_code == 404


async def test_update_suggested_edge_only_pending(
    client, db_session, sample_node, second_node, sample_edge_type
):
    """PATCH /api/parlementair/edges/{id} rejects update if edge is not pending."""
    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    se = await _create_suggested_edge(
        db_session, item.id, second_node.id, sample_edge_type.id
    )
    # Approve it first
    await client.put(f"/api/parlementair/edges/{se.id}/approve")

    # Try to update the now-approved edge
    resp = await client.patch(
        f"/api/parlementair/edges/{se.id}",
        json={"edge_type_id": "some_other_type"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Reset suggested edge
# ---------------------------------------------------------------------------


async def test_reset_suggested_edge_from_approved(
    client, db_session, sample_node, second_node, sample_edge_type
):
    """PUT /api/parlementair/edges/{id}/reset reverts approved edge to pending."""
    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    se = await _create_suggested_edge(
        db_session, item.id, second_node.id, sample_edge_type.id
    )
    # Approve first
    approve_resp = await client.put(f"/api/parlementair/edges/{se.id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"
    assert approve_resp.json()["edge_id"] is not None

    # Reset back to pending
    resp = await client.put(f"/api/parlementair/edges/{se.id}/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["edge_id"] is None


async def test_reset_suggested_edge_from_rejected(
    client, db_session, sample_node, second_node, sample_edge_type
):
    """PUT /api/parlementair/edges/{id}/reset reverts rejected edge to pending."""
    item = await _create_parlementair_item(
        db_session, corpus_node_id=sample_node.id, status="imported"
    )
    se = await _create_suggested_edge(
        db_session, item.id, second_node.id, sample_edge_type.id
    )
    # Reject first
    await client.put(f"/api/parlementair/edges/{se.id}/reject")

    # Reset back to pending
    resp = await client.put(f"/api/parlementair/edges/{se.id}/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"


async def test_reset_suggested_edge_not_found(client):
    """PUT /api/parlementair/edges/{id}/reset returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/parlementair/edges/{fake_id}/reset")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search imports
# ---------------------------------------------------------------------------


async def test_search_imports_by_titel(client, db_session):
    """GET /api/parlementair/imports?search= filters by titel."""
    item = await _create_parlementair_item(db_session)
    resp = await client.get(
        "/api/parlementair/imports", params={"search": "Test motie"}
    )
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()}
    assert str(item.id) in ids


async def test_search_imports_by_onderwerp(client, db_session):
    """GET /api/parlementair/imports?search= filters by onderwerp."""
    item = await _create_parlementair_item(db_session)
    resp = await client.get(
        "/api/parlementair/imports", params={"search": "Test onderwerp"}
    )
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()}
    assert str(item.id) in ids


async def test_search_imports_by_zaak_nummer(client, db_session):
    """GET /api/parlementair/imports?search= filters by zaak_nummer."""
    item = await _create_parlementair_item(db_session)
    resp = await client.get(
        "/api/parlementair/imports", params={"search": "36200-VII-42"}
    )
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()}
    assert str(item.id) in ids


async def test_search_imports_no_match(client, db_session):
    """GET /api/parlementair/imports?search= returns empty for non-matching query."""
    await _create_parlementair_item(db_session)
    resp = await client.get(
        "/api/parlementair/imports", params={"search": "xyz-nonexistent-query"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


async def test_search_imports_rejects_too_long(client):
    """GET /api/parlementair/imports?search= rejects queries over 500 chars."""
    resp = await client.get(
        "/api/parlementair/imports", params={"search": "a" * 501}
    )
    assert resp.status_code == 422


async def test_search_imports_case_insensitive(client, db_session):
    """GET /api/parlementair/imports?search= is case insensitive."""
    item = await _create_parlementair_item(db_session)
    resp = await client.get(
        "/api/parlementair/imports", params={"search": "test MOTIE"}
    )
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()}
    assert str(item.id) in ids


async def test_search_combined_with_status_filter(client, db_session):
    """GET /api/parlementair/imports?search=&status= combines both filters."""
    await _create_parlementair_item(db_session, status="imported")
    resp = await client.get(
        "/api/parlementair/imports",
        params={"search": "Test motie", "status": "reviewed"},
    )
    assert resp.status_code == 200
    # Should not find it because status doesn't match
    assert len(resp.json()) == 0


# ---------------------------------------------------------------------------
# Reopen import
# ---------------------------------------------------------------------------


async def test_reopen_rejected_import(client, db_session):
    """PUT /api/parlementair/imports/{id}/reopen reopens a rejected item."""
    item = await _create_parlementair_item(db_session, status="rejected")
    resp = await client.put(f"/api/parlementair/imports/{item.id}/reopen")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "imported"
    assert data["reviewed_at"] is None


async def test_reopen_out_of_scope_import(client, db_session):
    """PUT /api/parlementair/imports/{id}/reopen reopens an out_of_scope item."""
    item = await _create_parlementair_item(db_session, status="out_of_scope")
    resp = await client.put(f"/api/parlementair/imports/{item.id}/reopen")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "imported"
    assert data["reviewed_at"] is None


async def test_reopen_imported_item_fails(client, db_session):
    """PUT /api/parlementair/imports/{id}/reopen rejects already-imported items."""
    item = await _create_parlementair_item(db_session, status="imported")
    resp = await client.put(f"/api/parlementair/imports/{item.id}/reopen")
    assert resp.status_code == 400


async def test_reopen_reviewed_item_fails(client, db_session):
    """PUT /api/parlementair/imports/{id}/reopen rejects reviewed items."""
    item = await _create_parlementair_item(db_session, status="reviewed")
    resp = await client.put(f"/api/parlementair/imports/{item.id}/reopen")
    assert resp.status_code == 400


async def test_reopen_not_found(client):
    """PUT /api/parlementair/imports/{id}/reopen returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/parlementair/imports/{fake_id}/reopen")
    assert resp.status_code == 404
