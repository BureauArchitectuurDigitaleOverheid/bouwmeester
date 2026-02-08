"""Tests for stakeholder CRUD endpoints on nodes."""

import uuid


async def test_add_stakeholder(client, sample_node, sample_person):
    """POST /api/nodes/{id}/stakeholders creates a stakeholder."""
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": str(sample_person.id), "rol": "eigenaar"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rol"] == "eigenaar"
    assert data["person"]["id"] == str(sample_person.id)
    assert data["person"]["naam"] == "Jan Tester"
    assert "id" in data


async def test_add_stakeholder_node_not_found(client, sample_person):
    """POST returns 404 for non-existent node."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/nodes/{fake_id}/stakeholders",
        json={"person_id": str(sample_person.id), "rol": "betrokken"},
    )
    assert resp.status_code == 404


async def test_add_stakeholder_person_not_found(client, sample_node):
    """POST returns 404 for non-existent person."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": fake_id, "rol": "betrokken"},
    )
    assert resp.status_code == 404


async def test_list_stakeholders_includes_added(client, sample_node, sample_person):
    """GET /api/nodes/{id}/stakeholders returns the added stakeholder."""
    await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": str(sample_person.id), "rol": "adviseur"},
    )
    resp = await client.get(f"/api/nodes/{sample_node.id}/stakeholders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["rol"] == "adviseur"


async def test_update_stakeholder_rol(client, sample_node, sample_person):
    """PUT /api/nodes/{id}/stakeholders/{sid} updates the rol."""
    create_resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": str(sample_person.id), "rol": "betrokken"},
    )
    sid = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/nodes/{sample_node.id}/stakeholders/{sid}",
        json={"rol": "eigenaar"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["rol"] == "eigenaar"


async def test_update_stakeholder_not_found(client, sample_node):
    """PUT returns 404 for non-existent stakeholder."""
    fake_id = str(uuid.uuid4())
    resp = await client.put(
        f"/api/nodes/{sample_node.id}/stakeholders/{fake_id}",
        json={"rol": "eigenaar"},
    )
    assert resp.status_code == 404


async def test_delete_stakeholder(client, sample_node, sample_person):
    """DELETE /api/nodes/{id}/stakeholders/{sid} removes it."""
    create_resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": str(sample_person.id), "rol": "betrokken"},
    )
    sid = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/nodes/{sample_node.id}/stakeholders/{sid}")
    assert del_resp.status_code == 204

    # Verify it's gone
    list_resp = await client.get(f"/api/nodes/{sample_node.id}/stakeholders")
    assert len(list_resp.json()) == 0


async def test_delete_stakeholder_not_found(client, sample_node):
    """DELETE returns 404 for non-existent stakeholder."""
    fake_id = str(uuid.uuid4())
    resp = await client.delete(f"/api/nodes/{sample_node.id}/stakeholders/{fake_id}")
    assert resp.status_code == 404
