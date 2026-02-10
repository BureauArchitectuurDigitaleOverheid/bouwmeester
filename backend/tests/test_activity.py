"""Comprehensive API tests for the activity / audit-log feature."""

import uuid


# ---------------------------------------------------------------------------
# Activity feed – basic
# ---------------------------------------------------------------------------


async def test_activity_feed_returns_paginated_response(client):
    """GET /api/activity/feed returns {items: [...], total: int}."""
    resp = await client.get("/api/activity/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


async def test_activity_feed_empty_by_default(client):
    """When no mutations have happened the feed should be empty."""
    resp = await client.get("/api/activity/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Activity feed – pagination
# ---------------------------------------------------------------------------


async def test_activity_feed_pagination(client, sample_person):
    """Create several activity records via node mutations and verify skip/limit."""
    # Create 5 nodes to generate 5 activity entries
    node_ids = []
    for i in range(5):
        resp = await client.post(
            "/api/nodes",
            json={
                "title": f"Pagination node {i}",
                "node_type": "dossier",
            },
            params={"actor_id": str(sample_person.id)},
        )
        assert resp.status_code == 201
        node_ids.append(resp.json()["id"])

    # Total should be at least 5
    full_resp = await client.get("/api/activity/feed", params={"limit": 200})
    assert full_resp.status_code == 200
    full_data = full_resp.json()
    assert full_data["total"] >= 5

    # Fetch with limit=2
    page1 = await client.get("/api/activity/feed", params={"limit": 2, "skip": 0})
    assert page1.status_code == 200
    page1_data = page1.json()
    assert len(page1_data["items"]) == 2
    # Total should still reflect the full count
    assert page1_data["total"] >= 5

    # Fetch next page
    page2 = await client.get("/api/activity/feed", params={"limit": 2, "skip": 2})
    assert page2.status_code == 200
    page2_data = page2.json()
    assert len(page2_data["items"]) == 2

    # Items on page1 and page2 should be different
    page1_ids = {item["id"] for item in page1_data["items"]}
    page2_ids = {item["id"] for item in page2_data["items"]}
    assert page1_ids.isdisjoint(page2_ids)


async def test_activity_feed_skip_beyond_total(client, sample_person):
    """Skipping past all records returns an empty list but correct total."""
    # Create one activity
    resp = await client.post(
        "/api/nodes",
        json={"title": "Skip test", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201

    feed = await client.get("/api/activity/feed", params={"skip": 9999})
    assert feed.status_code == 200
    data = feed.json()
    assert data["items"] == []
    assert data["total"] >= 1


# ---------------------------------------------------------------------------
# Activity feed – event_type filter
# ---------------------------------------------------------------------------


async def test_activity_feed_event_type_filter(client, sample_person, sample_node):
    """Filter feed by event_type prefix (e.g. 'node')."""
    # Create a node (generates node.created)
    create_resp = await client.post(
        "/api/nodes",
        json={"title": "Filter test node", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    created_node_id = create_resp.json()["id"]

    # Update the node (generates node.updated)
    update_resp = await client.put(
        f"/api/nodes/{created_node_id}",
        json={"title": "Filter test node updated"},
        params={"actor_id": str(sample_person.id)},
    )
    assert update_resp.status_code == 200

    # Filter by event_type "node" should include both
    feed = await client.get("/api/activity/feed", params={"event_type": "node"})
    assert feed.status_code == 200
    data = feed.json()
    assert data["total"] >= 2
    # All returned items should have event_type starting with "node"
    for item in data["items"]:
        assert item["event_type"].startswith("node")


async def test_activity_feed_event_type_filter_specific(
    client, sample_person, sample_node
):
    """Filter by a specific event_type like 'node.created'."""
    # Create a node
    resp = await client.post(
        "/api/nodes",
        json={"title": "Specific filter node", "node_type": "doel"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    # Update the node to generate a different event type
    await client.put(
        f"/api/nodes/{node_id}",
        json={"title": "Specific filter node v2"},
        params={"actor_id": str(sample_person.id)},
    )

    # Filter for "node.created" only
    feed = await client.get("/api/activity/feed", params={"event_type": "node.created"})
    assert feed.status_code == 200
    data = feed.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["event_type"] == "node.created"


async def test_activity_feed_event_type_filter_no_match(client, sample_person):
    """Filtering by an event_type with no matching records returns empty."""
    # Create a node to have at least one activity
    resp = await client.post(
        "/api/nodes",
        json={"title": "No match node", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201

    # Filter for a nonexistent event type
    feed = await client.get(
        "/api/activity/feed",
        params={"event_type": "nonexistent.event.type.xyz"},
    )
    assert feed.status_code == 200
    data = feed.json()
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Activity feed – actor_id filter
# ---------------------------------------------------------------------------


async def test_activity_feed_actor_id_filter(client, sample_person, second_person):
    """Filter feed by actor_id returns only activities from that actor."""
    # Create nodes as different actors
    resp1 = await client.post(
        "/api/nodes",
        json={"title": "Actor1 node", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/nodes",
        json={"title": "Actor2 node", "node_type": "dossier"},
        params={"actor_id": str(second_person.id)},
    )
    assert resp2.status_code == 201

    # Filter by sample_person
    feed = await client.get(
        "/api/activity/feed",
        params={"actor_id": str(sample_person.id)},
    )
    assert feed.status_code == 200
    data = feed.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["actor_id"] == str(sample_person.id)


# ---------------------------------------------------------------------------
# Node create generates activity
# ---------------------------------------------------------------------------


async def test_node_create_generates_activity(client, sample_person):
    """POST /api/nodes should create an activity entry with event_type node.created."""
    resp = await client.post(
        "/api/nodes",
        json={
            "title": "Activity test node",
            "node_type": "dossier",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    # Check activity feed
    feed_resp = await client.get("/api/activity/feed")
    assert feed_resp.status_code == 200
    data = feed_resp.json()
    assert data["total"] >= 1

    # Find the activity for our node
    activities = [a for a in data["items"] if a["node_id"] == node_id]
    assert len(activities) == 1
    assert activities[0]["event_type"] == "node.created"
    assert activities[0]["actor_id"] == str(sample_person.id)
    assert activities[0]["details"]["title"] == "Activity test node"
    assert activities[0]["details"]["node_type"] == "dossier"


async def test_node_create_without_actor(client):
    """POST /api/nodes without actor_id still creates activity with actor_id=None."""
    resp = await client.post(
        "/api/nodes",
        json={
            "title": "No actor node",
            "node_type": "instrument",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    activities = [a for a in data["items"] if a["node_id"] == node_id]
    assert len(activities) == 1
    assert activities[0]["event_type"] == "node.created"
    assert activities[0]["actor_id"] is None


# ---------------------------------------------------------------------------
# Node update generates activity
# ---------------------------------------------------------------------------


async def test_node_update_generates_activity(client, sample_person, sample_node):
    """PUT /api/nodes/{id} should create an activity entry with event_type node.updated."""
    node_id = str(sample_node.id)

    resp = await client.put(
        f"/api/nodes/{node_id}",
        json={"title": "Updated dossier title"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    activities = [a for a in data["items"] if a["node_id"] == node_id]
    assert len(activities) >= 1

    updated_activities = [a for a in activities if a["event_type"] == "node.updated"]
    assert len(updated_activities) == 1
    assert updated_activities[0]["actor_id"] == str(sample_person.id)
    assert updated_activities[0]["details"]["title"] == "Updated dossier title"


async def test_node_update_nonexistent_returns_404(client, sample_person):
    """PUT /api/nodes/{nonexistent} returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/nodes/{fake_id}",
        json={"title": "Ghost"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Node delete generates activity
# ---------------------------------------------------------------------------


async def test_node_delete_generates_activity(client, sample_person):
    """DELETE /api/nodes/{id} should create an activity entry with node.deleted.

    The node_id FK column is left NULL (entity already deleted), but the
    deleted node's ID is stored in details["node_id"].
    """
    # Create a node first
    create_resp = await client.post(
        "/api/nodes",
        json={"title": "To be deleted", "node_type": "beleidskader"},
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    node_id = create_resp.json()["id"]

    # Delete it — should return 204 and log node.deleted activity
    del_resp = await client.delete(
        f"/api/nodes/{node_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    # Check activity feed for node.deleted
    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    deleted_activities = [
        a
        for a in data["items"]
        if a["event_type"] == "node.deleted"
        and a.get("details", {}).get("node_id") == node_id
    ]
    assert len(deleted_activities) == 1
    assert deleted_activities[0]["details"]["title"] == "To be deleted"
    assert deleted_activities[0]["details"]["node_type"] == "beleidskader"
    # node_id FK column is NULL since the node is deleted
    assert deleted_activities[0]["node_id"] is None


async def test_node_delete_nonexistent_returns_404(client):
    """DELETE /api/nodes/{nonexistent} returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/nodes/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full lifecycle: create → update → delete generates three activity entries
# ---------------------------------------------------------------------------


async def test_node_full_lifecycle_generates_activities(client, sample_person):
    """Create, update, and delete a node — produces 3 activity entries.

    After deletion, the FK column (node_id) on create/update activities is
    SET NULL by the DB cascade, so we verify event types by actor filter.
    """
    actor_params = {"actor_id": str(sample_person.id)}

    # Create
    create_resp = await client.post(
        "/api/nodes",
        json={"title": "Lifecycle node", "node_type": "maatregel"},
        params=actor_params,
    )
    assert create_resp.status_code == 201
    node_id = create_resp.json()["id"]

    # Verify create+update present before delete
    await client.put(
        f"/api/nodes/{node_id}",
        json={"title": "Lifecycle node v2"},
        params=actor_params,
    )

    feed_before = await client.get(
        "/api/activity/feed", params={"actor_id": str(sample_person.id)}
    )
    before_types = {a["event_type"] for a in feed_before.json()["items"]}
    assert "node.created" in before_types
    assert "node.updated" in before_types

    # Delete
    del_resp = await client.delete(f"/api/nodes/{node_id}", params=actor_params)
    assert del_resp.status_code == 204

    # After delete, node.deleted event should appear
    feed_after = await client.get(
        "/api/activity/feed", params={"actor_id": str(sample_person.id)}
    )
    after_types = {a["event_type"] for a in feed_after.json()["items"]}
    assert "node.deleted" in after_types


# ---------------------------------------------------------------------------
# Task create generates activity
# ---------------------------------------------------------------------------


async def test_task_create_generates_activity(client, sample_person, sample_node):
    """POST /api/tasks should create an activity entry with event_type task.created."""
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Activity test task",
            "node_id": str(sample_node.id),
            "assignee_id": str(sample_person.id),
            "status": "open",
            "priority": "normaal",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    task_activities = [a for a in data["items"] if a.get("task_id") == task_id]
    assert len(task_activities) == 1
    assert task_activities[0]["event_type"] == "task.created"
    assert task_activities[0]["details"]["title"] == "Activity test task"
    assert task_activities[0]["node_id"] == str(sample_node.id)


# ---------------------------------------------------------------------------
# Activity response structure
# ---------------------------------------------------------------------------


async def test_activity_response_has_expected_fields(client, sample_person):
    """Each activity item should contain all expected fields."""
    resp = await client.post(
        "/api/nodes",
        json={"title": "Fields test", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201

    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    assert len(data["items"]) >= 1

    item = data["items"][0]
    expected_keys = {
        "id",
        "event_type",
        "actor_id",
        "actor_naam",
        "node_id",
        "task_id",
        "edge_id",
        "details",
        "created_at",
    }
    assert expected_keys.issubset(set(item.keys()))


async def test_activity_actor_naam_populated(client, sample_person):
    """The actor_naam field should be populated when actor_id is provided."""
    resp = await client.post(
        "/api/nodes",
        json={"title": "Actor naam test", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    activities = [a for a in data["items"] if a["node_id"] == node_id]
    assert len(activities) == 1
    assert activities[0]["actor_naam"] == "Jan Tester"


# ---------------------------------------------------------------------------
# Stakeholder activity
# ---------------------------------------------------------------------------


async def test_stakeholder_added_generates_activity(
    client, sample_person, second_person, sample_node
):
    """Adding a stakeholder to a node generates a stakeholder.added activity."""
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={
            "person_id": str(second_person.id),
            "rol": "eigenaar",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201

    feed_resp = await client.get("/api/activity/feed")
    data = feed_resp.json()
    stakeholder_activities = [
        a
        for a in data["items"]
        if a["event_type"] == "stakeholder.added"
        and a["node_id"] == str(sample_node.id)
    ]
    assert len(stakeholder_activities) >= 1
    assert stakeholder_activities[0]["details"]["person_id"] == str(second_person.id)
    assert stakeholder_activities[0]["details"]["rol"] == "eigenaar"


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


async def test_inbox_returns_200(client, sample_person):
    """GET /api/activity/inbox?person_id=... returns 200 and inbox structure."""
    resp = await client.get(
        "/api/activity/inbox", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    data = resp.json()
    # InboxResponse should have known keys
    assert isinstance(data, dict)


async def test_inbox_unknown_person(client):
    """Inbox returns 200 with empty data for unknown person."""
    fake_id = uuid.uuid4()
    resp = await client.get("/api/activity/inbox", params={"person_id": str(fake_id)})
    assert resp.status_code == 200


async def test_inbox_requires_person_id(client):
    """Inbox without person_id returns 422 (validation error)."""
    resp = await client.get("/api/activity/inbox")
    assert resp.status_code == 422
