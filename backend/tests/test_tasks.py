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


# ---------------------------------------------------------------------------
# Reorder subtasks
# ---------------------------------------------------------------------------


async def test_reorder_subtasks(client, sample_task, sample_node, db_session):
    """PUT /api/tasks/{id}/subtasks/reorder sets correct order."""
    from bouwmeester.models.task import Task

    sub_a = Task(
        id=uuid.uuid4(),
        title="Subtaak A",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="normaal",
    )
    sub_b = Task(
        id=uuid.uuid4(),
        title="Subtaak B",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="normaal",
    )
    sub_c = Task(
        id=uuid.uuid4(),
        title="Subtaak C",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="normaal",
    )
    db_session.add_all([sub_a, sub_b, sub_c])
    await db_session.flush()

    # Reorder: C, A, B
    resp = await client.put(
        f"/api/tasks/{sample_task.id}/subtasks/reorder",
        json={"task_ids": [str(sub_c.id), str(sub_a.id), str(sub_b.id)]},
    )
    assert resp.status_code == 200
    data = resp.json()
    titles = [t["title"] for t in data]
    assert titles == ["Subtaak C", "Subtaak A", "Subtaak B"]
    assert data[0]["order"] == 0
    assert data[1]["order"] == 1
    assert data[2]["order"] == 2


async def test_reorder_subtasks_nonexistent_parent(client):
    """PUT /api/tasks/{id}/subtasks/reorder returns 404 for non-existent parent."""
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/tasks/{fake_id}/subtasks/reorder",
        json={"task_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 404


async def test_reorder_subtasks_rejects_partial_list(
    client, sample_task, sample_node, db_session
):
    """Reorder returns 400 when only a subset of subtasks is provided."""
    from bouwmeester.models.task import Task

    sub_a = Task(
        id=uuid.uuid4(),
        title="Subtaak A",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="normaal",
    )
    sub_b = Task(
        id=uuid.uuid4(),
        title="Subtaak B",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="normaal",
    )
    db_session.add_all([sub_a, sub_b])
    await db_session.flush()

    # Send only one of the two subtasks
    resp = await client.put(
        f"/api/tasks/{sample_task.id}/subtasks/reorder",
        json={"task_ids": [str(sub_a.id)]},
    )
    assert resp.status_code == 400
    assert "Expected 2" in resp.json()["detail"]


async def test_reorder_subtasks_rejects_foreign_ids(
    client, sample_task, sample_node, db_session
):
    """Reorder returns 400 when task IDs don't belong to the parent."""
    from bouwmeester.models.task import Task

    sub = Task(
        id=uuid.uuid4(),
        title="Eigen subtaak",
        node_id=sample_node.id,
        parent_id=sample_task.id,
        status="open",
        priority="normaal",
    )
    unrelated = Task(
        id=uuid.uuid4(),
        title="Andere taak",
        node_id=sample_node.id,
        parent_id=None,
        status="open",
        priority="normaal",
    )
    db_session.add_all([sub, unrelated])
    await db_session.flush()

    resp = await client.put(
        f"/api/tasks/{sample_task.id}/subtasks/reorder",
        json={"task_ids": [str(unrelated.id), str(sub.id)]},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Work type
# ---------------------------------------------------------------------------


async def test_create_task_with_work_type(client, sample_node, sample_person):
    """POST /api/tasks with work_type stores and returns it."""
    payload = {
        "title": "Taak met werktype",
        "node_id": str(sample_node.id),
        "assignee_id": str(sample_person.id),
        "work_type": "Analyse",
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["work_type"] == "Analyse"


async def test_update_task_work_type(client, sample_task):
    """PUT /api/tasks/{id} can set and clear work_type."""
    # Set work_type
    resp = await client.put(
        f"/api/tasks/{sample_task.id}",
        json={"work_type": "Review"},
    )
    assert resp.status_code == 200
    assert resp.json()["work_type"] == "Review"

    # Clear work_type by sending null
    resp2 = await client.put(
        f"/api/tasks/{sample_task.id}",
        json={"work_type": None},
    )
    assert resp2.status_code == 200
    assert resp2.json()["work_type"] is None


async def test_get_work_types(client, sample_node, sample_person, db_session):
    """GET /api/tasks/work-types returns distinct work_type values."""
    from bouwmeester.models.task import Task

    for wt in ["Analyse", "Review", "Analyse"]:
        db_session.add(
            Task(
                id=uuid.uuid4(),
                title=f"Taak {wt}",
                node_id=sample_node.id,
                assignee_id=sample_person.id,
                status="open",
                priority="normaal",
                work_type=wt,
            )
        )
    await db_session.flush()

    resp = await client.get("/api/tasks/work-types")
    assert resp.status_code == 200
    data = resp.json()
    assert "Analyse" in data
    assert "Review" in data
    # Should be deduplicated
    assert data.count("Analyse") == 1


async def test_get_work_types_empty(client):
    """GET /api/tasks/work-types returns empty list when no tasks have work_type."""
    resp = await client.get("/api/tasks/work-types")
    assert resp.status_code == 200
    assert resp.json() == []
