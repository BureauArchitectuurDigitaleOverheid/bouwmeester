"""API tests for edge schema validation and CRUD."""

import uuid

# ---------------------------------------------------------------------------
# Helper to create a schema rule via API
# ---------------------------------------------------------------------------


async def _create_rule(client, from_type, to_type, edge_type_id):
    resp = await client.post(
        "/api/edge-schema-rules",
        json={
            "from_node_type": from_type,
            "to_node_type": to_type,
            "edge_type_id": edge_type_id,
        },
    )
    return resp


# ---------------------------------------------------------------------------
# Schema rules CRUD
# ---------------------------------------------------------------------------


async def test_list_rules_empty(client):
    """GET /api/edge-schema-rules returns 200 and empty list when no rules."""
    resp = await client.get("/api/edge-schema-rules")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_rule(client, sample_edge_type):
    """POST /api/edge-schema-rules creates a rule and returns 201."""
    resp = await _create_rule(client, "dossier", "doel", sample_edge_type.id)
    assert resp.status_code == 201
    data = resp.json()
    assert data["from_node_type"] == "dossier"
    assert data["to_node_type"] == "doel"
    assert data["edge_type_id"] == sample_edge_type.id
    assert "id" in data


async def test_delete_rule(client, sample_edge_type):
    """DELETE /api/edge-schema-rules/{id} deletes a rule."""
    resp = await _create_rule(client, "dossier", "doel", sample_edge_type.id)
    rule_id = resp.json()["id"]

    del_resp = await client.delete(f"/api/edge-schema-rules/{rule_id}")
    assert del_resp.status_code == 204


async def test_delete_rule_not_found(client):
    """DELETE /api/edge-schema-rules/{id} returns 404 for non-existent rule."""
    resp = await client.delete(f"/api/edge-schema-rules/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# No schema rules => everything allowed (backward compat)
# ---------------------------------------------------------------------------


async def test_create_edge_no_schema_rules_allows_everything(
    client, sample_node, second_node, sample_edge_type
):
    """When no schema rules exist, any edge type is allowed."""
    payload = {
        "from_node_id": str(sample_node.id),
        "to_node_id": str(second_node.id),
        "edge_type_id": sample_edge_type.id,
    }
    resp = await client.post("/api/edges", json=payload)
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Schema validation on edge creation
# ---------------------------------------------------------------------------


async def test_create_edge_valid_combination_succeeds(
    client, sample_node, second_node, sample_edge_type
):
    """Edge creation succeeds when a matching schema rule exists."""
    # sample_node is dossier, second_node is doel
    await _create_rule(client, "dossier", "doel", sample_edge_type.id)

    payload = {
        "from_node_id": str(sample_node.id),
        "to_node_id": str(second_node.id),
        "edge_type_id": sample_edge_type.id,
    }
    resp = await client.post("/api/edges", json=payload)
    assert resp.status_code == 201


async def test_create_edge_invalid_combination_returns_422(
    client, sample_node, second_node, sample_edge_type, db_session
):
    """Edge creation fails with 422 when no matching schema rule exists."""
    # Create a rule for a DIFFERENT combination so the schema is active
    from bouwmeester.models.edge_schema_rule import EdgeSchemaRule

    db_session.add(
        EdgeSchemaRule(
            from_node_type="instrument",
            to_node_type="probleem",
            edge_type_id=sample_edge_type.id,
        )
    )
    await db_session.flush()

    # Try to create edge dossier -> doel (not allowed)
    payload = {
        "from_node_id": str(sample_node.id),
        "to_node_id": str(second_node.id),
        "edge_type_id": sample_edge_type.id,
    }
    resp = await client.post("/api/edges", json=payload)
    assert resp.status_code == 422
    assert "niet toegestaan" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Valid edge types endpoint
# ---------------------------------------------------------------------------


async def test_valid_types_no_rules_returns_inactive(client):
    """GET /api/edge-types/valid returns schema_active=false when no rules."""
    resp = await client.get("/api/edge-types/valid")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_active"] is False
    assert data["edge_type_ids"] == []


async def test_valid_types_returns_filtered(client, sample_edge_type):
    """GET /api/edge-types/valid returns filtered edge types when rules exist."""
    await _create_rule(client, "dossier", "doel", sample_edge_type.id)

    resp = await client.get(
        "/api/edge-types/valid",
        params={"from_node_type": "dossier", "to_node_type": "doel"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_active"] is True
    assert sample_edge_type.id in data["edge_type_ids"]


async def test_valid_types_no_match_returns_empty(client, sample_edge_type):
    """GET /api/edge-types/valid returns empty list for unmatched node types."""
    await _create_rule(client, "dossier", "doel", sample_edge_type.id)

    resp = await client.get(
        "/api/edge-types/valid",
        params={"from_node_type": "instrument", "to_node_type": "effect"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_active"] is True
    assert data["edge_type_ids"] == []


async def test_valid_types_partial_filter(client, sample_edge_type):
    """GET /api/edge-types/valid with only from_node_type returns all types."""
    await _create_rule(client, "dossier", "doel", sample_edge_type.id)

    resp = await client.get(
        "/api/edge-types/valid",
        params={"from_node_type": "dossier"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_active"] is True
    assert sample_edge_type.id in data["edge_type_ids"]
