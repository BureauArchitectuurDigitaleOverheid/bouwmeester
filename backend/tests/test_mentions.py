"""Comprehensive API tests for the mentions router."""

import uuid

from bouwmeester.models.mention import Mention

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


# ---------------------------------------------------------------------------
# References privacy: only public source types (node, task) are returned
# ---------------------------------------------------------------------------


async def test_references_includes_node_source(client, db_session, sample_node):
    """A mention from a node source appears in references."""
    target_id = uuid.uuid4()
    mention = Mention(
        source_type="node",
        source_id=sample_node.id,
        mention_type="node",
        target_id=target_id,
    )
    db_session.add(mention)
    await db_session.flush()

    resp = await client.get(f"/api/mentions/references/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "node"


async def test_references_includes_task_source(
    client, db_session, sample_task, sample_node
):
    """A mention from a task source appears in references."""
    target_id = sample_node.id
    mention = Mention(
        source_type="task",
        source_id=sample_task.id,
        mention_type="node",
        target_id=target_id,
    )
    db_session.add(mention)
    await db_session.flush()

    resp = await client.get(f"/api/mentions/references/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    source_types = {r["source_type"] for r in data}
    assert "task" in source_types


async def test_references_excludes_notification_source(
    client, db_session, sample_node, sample_notification
):
    """A mention from a notification (DM) must NOT appear in references."""
    target_id = sample_node.id
    mention = Mention(
        source_type="notification",
        source_id=sample_notification.id,
        mention_type="node",
        target_id=target_id,
    )
    db_session.add(mention)
    await db_session.flush()

    resp = await client.get(f"/api/mentions/references/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    source_types = {r["source_type"] for r in data}
    assert "notification" not in source_types


async def test_references_excludes_organisatie_source(client, db_session, sample_node):
    """A mention from an organisatie source must NOT appear in references."""
    target_id = sample_node.id
    org_id = uuid.uuid4()
    mention = Mention(
        source_type="organisatie",
        source_id=org_id,
        mention_type="node",
        target_id=target_id,
    )
    db_session.add(mention)
    await db_session.flush()

    resp = await client.get(f"/api/mentions/references/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    source_types = {r["source_type"] for r in data}
    assert "organisatie" not in source_types


async def test_references_mixed_sources_only_public(
    client, db_session, sample_node, sample_task, sample_notification
):
    """With mixed source types, only node and task references are returned."""
    target_id = uuid.uuid4()

    for source_type, source_id in [
        ("node", sample_node.id),
        ("task", sample_task.id),
        ("notification", sample_notification.id),
        ("organisatie", uuid.uuid4()),
    ]:
        db_session.add(
            Mention(
                source_type=source_type,
                source_id=source_id,
                mention_type="node",
                target_id=target_id,
            )
        )
    await db_session.flush()

    resp = await client.get(f"/api/mentions/references/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    source_types = {r["source_type"] for r in data}
    assert source_types == {"node", "task"}
