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
    """Feed with a non-existent actor_id filter should return zero results."""
    resp = await client.get(
        "/api/activity/feed",
        params={"actor_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Activity feed – pagination
# ---------------------------------------------------------------------------


async def test_activity_feed_pagination(client, sample_person):
    """Create several activity records via node mutations and verify skip/limit."""
    # Use actor_id filter so we only see activities from this test
    actor_id = str(sample_person.id)

    # Create 5 nodes to generate 5 activity entries
    node_ids = []
    for i in range(5):
        resp = await client.post(
            "/api/nodes",
            json={
                "title": f"Pagination node {i}",
                "node_type": "dossier",
            },
            params={"actor_id": actor_id},
        )
        assert resp.status_code == 201
        node_ids.append(resp.json()["id"])

    # Total should be at least 5 for this actor
    full_resp = await client.get(
        "/api/activity/feed", params={"limit": 200, "actor_id": actor_id}
    )
    assert full_resp.status_code == 200
    full_data = full_resp.json()
    assert full_data["total"] >= 5

    # Fetch with limit=2
    page1 = await client.get(
        "/api/activity/feed", params={"limit": 2, "skip": 0, "actor_id": actor_id}
    )
    assert page1.status_code == 200
    page1_data = page1.json()
    assert len(page1_data["items"]) == 2
    assert page1_data["total"] >= 5

    # Fetch next page
    page2 = await client.get(
        "/api/activity/feed", params={"limit": 2, "skip": 2, "actor_id": actor_id}
    )
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


# ---------------------------------------------------------------------------
# Edge CRUD generates activity
# ---------------------------------------------------------------------------


async def test_edge_create_generates_activity(
    client, sample_person, sample_node, second_node, sample_edge_type
):
    """POST /api/edges should create edge.created activity."""
    resp = await client.post(
        "/api/edges",
        json={
            "from_node_id": str(sample_node.id),
            "to_node_id": str(second_node.id),
            "edge_type_id": sample_edge_type.id,
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    edge_id = resp.json()["id"]

    feed = await client.get("/api/activity/feed", params={"event_type": "edge.created"})
    data = feed.json()
    activities = [a for a in data["items"] if a.get("edge_id") == edge_id]
    assert len(activities) == 1
    assert activities[0]["details"]["from_node_id"] == str(sample_node.id)
    assert activities[0]["details"]["to_node_id"] == str(second_node.id)
    assert activities[0]["details"]["edge_type"] == sample_edge_type.id


async def test_edge_update_generates_activity(
    client, sample_person, sample_edge, sample_edge_type
):
    """PUT /api/edges/{id} should create edge.updated activity."""
    resp = await client.put(
        f"/api/edges/{sample_edge.id}",
        json={"edge_type_id": sample_edge_type.id},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed = await client.get("/api/activity/feed", params={"event_type": "edge.updated"})
    data = feed.json()
    activities = [a for a in data["items"] if a.get("edge_id") == str(sample_edge.id)]
    assert len(activities) == 1
    assert activities[0]["details"]["edge_type"] == sample_edge_type.id


async def test_edge_delete_generates_activity(
    client, sample_person, sample_node, second_node, sample_edge_type
):
    """DELETE /api/edges/{id} should create edge.deleted activity with IDs in details."""
    # Create an edge to delete
    create_resp = await client.post(
        "/api/edges",
        json={
            "from_node_id": str(sample_node.id),
            "to_node_id": str(second_node.id),
            "edge_type_id": sample_edge_type.id,
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    edge_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/edges/{edge_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get("/api/activity/feed", params={"event_type": "edge.deleted"})
    data = feed.json()
    deleted = [
        a
        for a in data["items"]
        if a["event_type"] == "edge.deleted"
        and a.get("details", {}).get("edge_id") == edge_id
    ]
    assert len(deleted) == 1
    assert deleted[0]["details"]["from_node_id"] == str(sample_node.id)
    assert deleted[0]["details"]["to_node_id"] == str(second_node.id)
    # edge_id FK column is NULL after deletion
    assert deleted[0]["edge_id"] is None


# ---------------------------------------------------------------------------
# Task update / delete generate activity
# ---------------------------------------------------------------------------


async def test_task_update_generates_activity(client, sample_person, sample_node):
    """PUT /api/tasks/{id} should create task.updated activity."""
    # Create a task first
    create_resp = await client.post(
        "/api/tasks",
        json={
            "title": "Update test task",
            "node_id": str(sample_node.id),
            "status": "open",
            "priority": "normaal",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Update the task
    update_resp = await client.put(
        f"/api/tasks/{task_id}",
        json={"title": "Updated task title"},
        params={"actor_id": str(sample_person.id)},
    )
    assert update_resp.status_code == 200

    feed = await client.get("/api/activity/feed", params={"event_type": "task.updated"})
    data = feed.json()
    activities = [a for a in data["items"] if a.get("task_id") == task_id]
    assert len(activities) == 1
    assert activities[0]["details"]["title"] == "Updated task title"


async def test_task_delete_generates_activity(client, sample_person, sample_node):
    """DELETE /api/tasks/{id} should create task.deleted activity with IDs in details."""
    # Create a task first
    create_resp = await client.post(
        "/api/tasks",
        json={
            "title": "Delete test task",
            "node_id": str(sample_node.id),
            "status": "open",
            "priority": "normaal",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/tasks/{task_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get("/api/activity/feed", params={"event_type": "task.deleted"})
    data = feed.json()
    deleted = [
        a
        for a in data["items"]
        if a["event_type"] == "task.deleted"
        and a.get("details", {}).get("task_id") == task_id
    ]
    assert len(deleted) == 1
    assert deleted[0]["details"]["title"] == "Delete test task"


# ---------------------------------------------------------------------------
# Person CRUD generates activity
# ---------------------------------------------------------------------------


async def test_person_create_generates_activity(client, sample_person):
    """POST /api/people should create person.created activity."""
    resp = await client.post(
        "/api/people",
        json={"naam": "Audit Persoon", "email": "audit@example.com"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    person_id = resp.json()["id"]

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "person.created"}
    )
    data = feed.json()
    activities = [
        a for a in data["items"] if a.get("details", {}).get("person_id") == person_id
    ]
    assert len(activities) == 1
    assert activities[0]["details"]["naam"] == "Audit Persoon"


async def test_person_update_generates_activity(client, sample_person):
    """PUT /api/people/{id} should create person.updated activity."""
    resp = await client.put(
        f"/api/people/{sample_person.id}",
        json={"naam": "Jan Gewijzigd"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "person.updated"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a.get("details", {}).get("person_id") == str(sample_person.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["naam"] == "Jan Gewijzigd"


async def test_person_delete_generates_activity(client, sample_person):
    """DELETE /api/people/{id} should create person.deleted activity."""
    # Create a person to delete (don't delete fixtures)
    create_resp = await client.post(
        "/api/people",
        json={"naam": "Te Verwijderen", "email": "del@example.com"},
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    person_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/people/{person_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "person.deleted"}
    )
    data = feed.json()
    deleted = [
        a for a in data["items"] if a.get("details", {}).get("person_id") == person_id
    ]
    assert len(deleted) == 1
    assert deleted[0]["details"]["naam"] == "Te Verwijderen"


# ---------------------------------------------------------------------------
# Organisatie CRUD generates activity
# ---------------------------------------------------------------------------


async def test_organisatie_create_generates_activity(client, sample_person):
    """POST /api/organisatie should create organisatie.created activity."""
    resp = await client.post(
        "/api/organisatie",
        json={"naam": "Audit Ministerie", "type": "ministerie"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    org_id = resp.json()["id"]

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "organisatie.created"}
    )
    data = feed.json()
    activities = [
        a for a in data["items"] if a.get("details", {}).get("organisatie_id") == org_id
    ]
    assert len(activities) == 1
    assert activities[0]["details"]["naam"] == "Audit Ministerie"


async def test_organisatie_update_generates_activity(
    client, sample_person, sample_organisatie
):
    """PUT /api/organisatie/{id} should create organisatie.updated activity."""
    resp = await client.put(
        f"/api/organisatie/{sample_organisatie.id}",
        json={"naam": "Gewijzigd Ministerie"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "organisatie.updated"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a.get("details", {}).get("organisatie_id") == str(sample_organisatie.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["naam"] == "Gewijzigd Ministerie"


async def test_organisatie_delete_generates_activity(client, sample_person):
    """DELETE /api/organisatie/{id} should create organisatie.deleted activity."""
    # Create an org unit to delete (no children, no personen)
    create_resp = await client.post(
        "/api/organisatie",
        json={"naam": "Te Verwijderen Org", "type": "afdeling"},
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    org_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/organisatie/{org_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "organisatie.deleted"}
    )
    data = feed.json()
    deleted = [
        a for a in data["items"] if a.get("details", {}).get("organisatie_id") == org_id
    ]
    assert len(deleted) == 1
    assert deleted[0]["details"]["naam"] == "Te Verwijderen Org"


# ---------------------------------------------------------------------------
# Tag CRUD generates activity
# ---------------------------------------------------------------------------


async def test_tag_create_generates_activity(client, sample_person):
    """POST /api/tags should create tag.created activity."""
    resp = await client.post(
        "/api/tags",
        json={"name": "Audit Tag"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    tag_id = resp.json()["id"]

    feed = await client.get("/api/activity/feed", params={"event_type": "tag.created"})
    data = feed.json()
    activities = [
        a for a in data["items"] if a.get("details", {}).get("tag_id") == tag_id
    ]
    assert len(activities) == 1
    assert activities[0]["details"]["name"] == "Audit Tag"


async def test_tag_update_generates_activity(client, sample_person, sample_tag):
    """PUT /api/tags/{id} should create tag.updated activity."""
    resp = await client.put(
        f"/api/tags/{sample_tag.id}",
        json={"name": "Updated Tag"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed = await client.get("/api/activity/feed", params={"event_type": "tag.updated"})
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a.get("details", {}).get("tag_id") == str(sample_tag.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["name"] == "Updated Tag"


async def test_tag_delete_generates_activity(client, sample_person):
    """DELETE /api/tags/{id} should create tag.deleted activity."""
    # Create a tag to delete
    create_resp = await client.post(
        "/api/tags",
        json={"name": "Te Verwijderen Tag"},
        params={"actor_id": str(sample_person.id)},
    )
    assert create_resp.status_code == 201
    tag_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/tags/{tag_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get("/api/activity/feed", params={"event_type": "tag.deleted"})
    data = feed.json()
    deleted = [a for a in data["items"] if a.get("details", {}).get("tag_id") == tag_id]
    assert len(deleted) == 1
    assert deleted[0]["details"]["name"] == "Te Verwijderen Tag"


# ---------------------------------------------------------------------------
# Node tag add/remove generates activity
# ---------------------------------------------------------------------------


async def test_node_tag_add_generates_activity(
    client, sample_person, sample_node, sample_tag
):
    """POST /api/nodes/{id}/tags should create node_tag.added activity."""
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/tags",
        json={"tag_id": str(sample_tag.id)},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "node_tag.added"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a["event_type"] == "node_tag.added" and a["node_id"] == str(sample_node.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["tag_id"] == str(sample_tag.id)


async def test_node_tag_remove_generates_activity(
    client, sample_person, sample_node, sample_tag
):
    """DELETE /api/nodes/{id}/tags/{tag_id} should create node_tag.removed activity."""
    # First add the tag
    add_resp = await client.post(
        f"/api/nodes/{sample_node.id}/tags",
        json={"tag_id": str(sample_tag.id)},
        params={"actor_id": str(sample_person.id)},
    )
    assert add_resp.status_code == 201

    # Remove the tag
    del_resp = await client.delete(
        f"/api/nodes/{sample_node.id}/tags/{sample_tag.id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "node_tag.removed"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a["event_type"] == "node_tag.removed" and a["node_id"] == str(sample_node.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["tag_id"] == str(sample_tag.id)


# ---------------------------------------------------------------------------
# Stakeholder update/remove generates activity
# ---------------------------------------------------------------------------


async def test_stakeholder_updated_generates_activity(
    client, sample_person, second_person, sample_node
):
    """PUT /api/nodes/{id}/stakeholders/{sid} should create stakeholder.updated."""
    # Add a stakeholder first
    add_resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": str(second_person.id), "rol": "betrokken"},
        params={"actor_id": str(sample_person.id)},
    )
    assert add_resp.status_code == 201
    stakeholder_id = add_resp.json()["id"]

    # Update the stakeholder role
    update_resp = await client.put(
        f"/api/nodes/{sample_node.id}/stakeholders/{stakeholder_id}",
        json={"rol": "eigenaar"},
        params={"actor_id": str(sample_person.id)},
    )
    assert update_resp.status_code == 200

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "stakeholder.updated"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a["event_type"] == "stakeholder.updated"
        and a["node_id"] == str(sample_node.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["old_rol"] == "betrokken"
    assert activities[0]["details"]["new_rol"] == "eigenaar"


async def test_stakeholder_removed_generates_activity(
    client, sample_person, second_person, sample_node
):
    """DELETE /api/nodes/{id}/stakeholders/{sid} should create stakeholder.removed."""
    # Add a stakeholder first
    add_resp = await client.post(
        f"/api/nodes/{sample_node.id}/stakeholders",
        json={"person_id": str(second_person.id), "rol": "adviseur"},
        params={"actor_id": str(sample_person.id)},
    )
    assert add_resp.status_code == 201
    stakeholder_id = add_resp.json()["id"]

    # Remove the stakeholder
    del_resp = await client.delete(
        f"/api/nodes/{sample_node.id}/stakeholders/{stakeholder_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "stakeholder.removed"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a["event_type"] == "stakeholder.removed"
        and a["node_id"] == str(sample_node.id)
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["person_id"] == str(second_person.id)
    assert activities[0]["details"]["rol"] == "adviseur"


# ---------------------------------------------------------------------------
# Person organisatie placement generates activity
# ---------------------------------------------------------------------------


async def test_person_organisatie_added_generates_activity(
    client, sample_person, sample_organisatie
):
    """POST /api/people/{id}/organisaties should create person.organisatie_added."""
    resp = await client.post(
        f"/api/people/{sample_person.id}/organisaties",
        json={
            "organisatie_eenheid_id": str(sample_organisatie.id),
            "dienstverband": "in_dienst",
            "start_datum": "2024-01-01",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "person.organisatie_added"}
    )
    data = feed.json()
    assert data["total"] >= 1
    activities = [
        a for a in data["items"] if a["event_type"] == "person.organisatie_added"
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["person_id"] == str(sample_person.id)
    assert activities[0]["details"]["organisatie_eenheid_id"] == str(
        sample_organisatie.id
    )


async def test_person_organisatie_removed_generates_activity(
    client, sample_person, sample_organisatie
):
    """DELETE /api/people/{id}/organisaties/{pid} creates person.organisatie_removed."""
    # Add a placement first
    add_resp = await client.post(
        f"/api/people/{sample_person.id}/organisaties",
        json={
            "organisatie_eenheid_id": str(sample_organisatie.id),
            "dienstverband": "in_dienst",
            "start_datum": "2024-01-01",
        },
        params={"actor_id": str(sample_person.id)},
    )
    assert add_resp.status_code == 201
    placement_id = add_resp.json()["id"]

    # Remove the placement
    del_resp = await client.delete(
        f"/api/people/{sample_person.id}/organisaties/{placement_id}",
        params={"actor_id": str(sample_person.id)},
    )
    assert del_resp.status_code == 204

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "person.organisatie_removed"}
    )
    data = feed.json()
    assert data["total"] >= 1
    activities = [
        a for a in data["items"] if a["event_type"] == "person.organisatie_removed"
    ]
    assert len(activities) >= 1
    assert activities[0]["details"]["person_id"] == str(sample_person.id)


# ---------------------------------------------------------------------------
# Parlementair generates activity
# ---------------------------------------------------------------------------


async def test_parlementair_reject_generates_activity(
    client, db_session, sample_person, sample_node
):
    """PUT /api/parlementair/imports/{id}/reject creates parlementair.rejected."""
    from bouwmeester.models.parlementair_item import ParlementairItem

    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer=f"36200-{uuid.uuid4().hex[:4]}",
        titel="Reject test",
        onderwerp="Test",
        bron="tweede_kamer",
        status="pending",
        corpus_node_id=sample_node.id,
    )
    db_session.add(item)
    await db_session.flush()

    resp = await client.put(
        f"/api/parlementair/imports/{item.id}/reject",
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "parlementair.rejected"}
    )
    data = feed.json()
    activities = [
        a for a in data["items"] if a.get("details", {}).get("item_id") == str(item.id)
    ]
    assert len(activities) == 1


async def test_parlementair_edge_approve_generates_activity(
    client, db_session, sample_person, sample_node, second_node, sample_edge_type
):
    """PUT /api/parlementair/edges/{id}/approve creates parlementair.edge_approved."""
    from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge

    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer=f"36200-{uuid.uuid4().hex[:4]}",
        titel="Edge approve test",
        onderwerp="Test",
        bron="tweede_kamer",
        status="pending",
        corpus_node_id=sample_node.id,
    )
    db_session.add(item)
    await db_session.flush()

    se = SuggestedEdge(
        id=uuid.uuid4(),
        parlementair_item_id=item.id,
        target_node_id=second_node.id,
        edge_type_id=sample_edge_type.id,
        confidence=0.9,
        reason="Test",
        status="pending",
    )
    db_session.add(se)
    await db_session.flush()

    resp = await client.put(
        f"/api/parlementair/edges/{se.id}/approve",
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 200

    feed = await client.get(
        "/api/activity/feed", params={"event_type": "parlementair.edge_approved"}
    )
    data = feed.json()
    activities = [
        a
        for a in data["items"]
        if a.get("details", {}).get("suggested_edge_id") == str(se.id)
    ]
    assert len(activities) == 1


# ---------------------------------------------------------------------------
# actor_naam denormalized in details
# ---------------------------------------------------------------------------


async def test_actor_naam_stored_in_details(client, sample_person):
    """Activity details should include actor_naam for attribution durability.

    resolve_actor_naam_from_db looks up the person via actor_id when
    current_user is None (dev mode), so actor_naam is denormalized into
    details regardless of auth mode.
    """
    resp = await client.post(
        "/api/nodes",
        json={"title": "Naam in details test", "node_type": "dossier"},
        params={"actor_id": str(sample_person.id)},
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    feed = await client.get("/api/activity/feed")
    data = feed.json()
    activities = [a for a in data["items"] if a["node_id"] == node_id]
    assert len(activities) == 1
    # Top-level actor_naam is resolved via the Person relationship
    assert activities[0]["actor_naam"] == "Jan Tester"
    # actor_naam is also denormalized into details for durability
    assert activities[0]["details"].get("actor_naam") == "Jan Tester"
