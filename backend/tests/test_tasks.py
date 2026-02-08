"""Tests for task CRUD endpoints."""

import uuid


async def test_list_tasks_returns_ok(client):
    """GET /api/tasks returns 200 with a list."""
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_tasks_with_data(client, sample_task):
    """GET /api/tasks returns tasks when they exist."""
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    titles = [t["title"] for t in data]
    assert "Test taak" in titles


async def test_list_tasks_filtered_by_status(client, sample_task):
    """GET /api/tasks?status=open returns only open tasks."""
    resp = await client.get("/api/tasks", params={"status": "open"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(t["status"] == "open" for t in data)

    # Filter by cancelled — sample_task is open, so it should not appear
    resp2 = await client.get("/api/tasks", params={"status": "cancelled"})
    assert resp2.status_code == 200
    cancelled_ids = [t["id"] for t in resp2.json()]
    assert str(sample_task.id) not in cancelled_ids


async def test_create_task(client, sample_node, sample_person):
    """POST /api/tasks creates a new task."""
    payload = {
        "title": "Nieuwe taak",
        "description": "Beschrijving van de taak",
        "node_id": str(sample_node.id),
        "assignee_id": str(sample_person.id),
        "status": "open",
        "priority": "hoog",
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Nieuwe taak"
    assert data["description"] == "Beschrijving van de taak"
    assert data["node_id"] == str(sample_node.id)
    assert data["assignee_id"] == str(sample_person.id)
    assert data["status"] == "open"
    assert data["priority"] == "hoog"
    assert "id" in data
    assert "created_at" in data


async def test_create_task_missing_node_id(client):
    """POST /api/tasks without node_id returns 422."""
    payload = {
        "title": "Taak zonder node",
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 422


async def test_get_task_by_id(client, sample_task):
    """GET /api/tasks/{id} returns the task."""
    resp = await client.get(f"/api/tasks/{sample_task.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_task.id)
    assert data["title"] == "Test taak"
    assert data["status"] == "open"
    assert data["priority"] == "normaal"


async def test_get_task_not_found(client):
    """GET /api/tasks/{id} returns 404 for non-existent task."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/tasks/{fake_id}")
    assert resp.status_code == 404


async def test_update_task_status(client, sample_task):
    """PUT /api/tasks/{id} updates the task."""
    resp = await client.put(
        f"/api/tasks/{sample_task.id}",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["id"] == str(sample_task.id)


async def test_update_task_not_found(client):
    """PUT /api/tasks/{id} returns 404 for non-existent task."""
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/tasks/{fake_id}",
        json={"status": "done"},
    )
    assert resp.status_code == 404


async def test_delete_task(client, sample_task):
    """DELETE /api/tasks/{id} deletes the task and returns 204."""
    resp = await client.delete(f"/api/tasks/{sample_task.id}")
    assert resp.status_code == 204

    # Verify it is gone
    get_resp = await client.get(f"/api/tasks/{sample_task.id}")
    assert get_resp.status_code == 404


async def test_delete_task_not_found(client):
    """DELETE /api/tasks/{id} returns 404 for non-existent task."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/tasks/{fake_id}")
    assert resp.status_code == 404


async def test_get_my_tasks(client, sample_task, sample_person):
    """GET /api/tasks/my?person_id=... returns tasks for that person."""
    resp = await client.get(
        "/api/tasks/my",
        params={"person_id": str(sample_person.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(t["assignee_id"] == str(sample_person.id) for t in data)


async def test_get_unassigned_tasks(client, sample_node, db_session):
    """GET /api/tasks/unassigned returns tasks without an assignee."""
    from bouwmeester.models.task import Task

    unassigned = Task(
        id=uuid.uuid4(),
        title="Onverdeelde taak",
        node_id=sample_node.id,
        assignee_id=None,
        status="open",
        priority="normaal",
    )
    db_session.add(unassigned)
    await db_session.flush()

    resp = await client.get("/api/tasks/unassigned")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(t["title"] == "Onverdeelde taak" for t in data)
    assert all(t["assignee_id"] is None for t in data)


async def test_get_task_subtasks(client, sample_task, sample_node, db_session):
    """GET /api/tasks/{id}/subtasks returns child tasks."""
    from bouwmeester.models.task import Task

    subtask = Task(
        id=uuid.uuid4(),
        title="Subtaak",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="laag",
    )
    db_session.add(subtask)
    await db_session.flush()

    resp = await client.get(f"/api/tasks/{sample_task.id}/subtasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Subtaak"
    assert data[0]["status"] == "open"
    assert data[0]["priority"] == "laag"
