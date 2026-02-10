"""Comprehensive API tests for the notifications router."""

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.config import get_settings
from bouwmeester.core.database import get_db

settings = get_settings()

# ---------------------------------------------------------------------------
# List notifications
# ---------------------------------------------------------------------------


async def test_list_notifications_returns_200(client, sample_person):
    """GET /api/notifications?person_id=... returns 200 and a list."""
    resp = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_notifications_includes_fixture(
    client, sample_person, sample_notification
):
    """GET /api/notifications?person_id=... includes the fixture notification."""
    resp = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {n["id"] for n in data}
    assert str(sample_notification.id) in ids


async def test_list_notifications_unread_only(
    client, sample_person, sample_notification
):
    """GET /api/notifications?person_id=...&unread_only=true filters unread."""
    resp = await client.get(
        "/api/notifications",
        params={"person_id": str(sample_person.id), "unread_only": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(n["is_read"] is False for n in data)
    ids = {n["id"] for n in data}
    assert str(sample_notification.id) in ids


async def test_list_notifications_enriches_sender_name(
    client, sample_person, sample_notification
):
    """GET /api/notifications includes sender_name from batch enrichment."""
    resp = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    data = resp.json()
    notif = next(n for n in data if n["id"] == str(sample_notification.id))
    assert notif["sender_name"] is not None
    assert notif["sender_name"] == "Piet Tester"


async def test_list_notifications_excludes_replies(
    client, db_session, sample_person, sample_notification, second_person
):
    """GET /api/notifications only returns root notifications, not replies."""
    from bouwmeester.models.notification import Notification

    reply = Notification(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        type="direct_message",
        title="Reactie",
        message="Een reactie",
        sender_id=second_person.id,
        parent_id=sample_notification.id,
        is_read=False,
    )
    db_session.add(reply)
    await db_session.flush()

    resp = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = {n["id"] for n in data}
    assert str(reply.id) not in ids
    assert str(sample_notification.id) in ids


# ---------------------------------------------------------------------------
# Get single notification
# ---------------------------------------------------------------------------


async def test_get_notification(client, sample_notification):
    """GET /api/notifications/{id} returns the notification with enrichment."""
    resp = await client.get(f"/api/notifications/{sample_notification.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_notification.id)
    assert data["sender_name"] == "Piet Tester"


async def test_get_notification_not_found(client):
    """GET /api/notifications/{id} returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/notifications/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unread count
# ---------------------------------------------------------------------------


async def test_unread_count_returns_count(client, sample_person, sample_notification):
    """GET /api/notifications/count?person_id=... returns unread count."""
    resp = await client.get(
        "/api/notifications/count", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert data["count"] >= 1


async def test_unread_count_zero_for_unknown(client):
    """GET /api/notifications/count?person_id=... returns 0 for unknown person."""
    fake_id = uuid.uuid4()
    resp = await client.get(
        "/api/notifications/count", params={"person_id": str(fake_id)}
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_unread_count_excludes_replies(
    client, db_session, sample_person, sample_notification, second_person
):
    """Unread count only counts root notifications, matching the list view."""
    from bouwmeester.models.notification import Notification

    # Get baseline count
    resp = await client.get(
        "/api/notifications/count", params={"person_id": str(sample_person.id)}
    )
    baseline = resp.json()["count"]

    # Add a reply (should NOT increase count)
    reply = Notification(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        type="direct_message",
        title="Reactie",
        message="Een reactie",
        sender_id=second_person.id,
        parent_id=sample_notification.id,
        is_read=False,
    )
    db_session.add(reply)
    await db_session.flush()

    resp = await client.get(
        "/api/notifications/count", params={"person_id": str(sample_person.id)}
    )
    assert resp.json()["count"] == baseline


# ---------------------------------------------------------------------------
# Mark read
# ---------------------------------------------------------------------------


async def test_mark_notification_read(client, sample_notification):
    """PUT /api/notifications/{id}/read marks notification as read."""
    resp = await client.put(f"/api/notifications/{sample_notification.id}/read")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_read"] is True


async def test_mark_notification_read_not_found(client):
    """PUT /api/notifications/{id}/read returns 404 for non-existent."""
    fake_id = uuid.uuid4()
    resp = await client.put(f"/api/notifications/{fake_id}/read")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mark all read
# ---------------------------------------------------------------------------


async def test_mark_all_read(client, sample_person, sample_notification):
    """PUT /api/notifications/read-all?person_id=... marks all as read."""
    resp = await client.put(
        "/api/notifications/read-all",
        params={"person_id": str(sample_person.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "marked_read" in data
    assert data["marked_read"] >= 1


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------


async def test_send_message(client, sample_person, second_person):
    """POST /api/notifications/send creates a direct message notification.

    The endpoint returns the *sender's* root (so the sender can see it
    in their inbox immediately).  The recipient also gets their own root.
    """
    payload = {
        "person_id": str(sample_person.id),
        "sender_id": str(second_person.id),
        "message": "Hallo, dit is een testbericht!",
    }
    resp = await client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Response is the sender's root
    assert data["person_id"] == str(second_person.id)
    assert data["type"] == "direct_message"
    assert "Bericht aan" in data["title"]

    # Recipient should also have received their own root
    inbox = await client.get(
        "/api/notifications",
        params={"person_id": str(sample_person.id)},
    )
    recipient_dm = [
        n for n in inbox.json() if n["type"] == "direct_message" and not n["is_read"]
    ]
    assert len(recipient_dm) >= 1
    assert any("Bericht van" in n["title"] for n in recipient_dm)


async def test_dm_sender_sees_conversation_in_inbox(
    client, sample_person, second_person
):
    """DM sender can see the conversation root in their inbox."""
    # second_person sends DM to sample_person
    payload = {
        "person_id": str(sample_person.id),
        "sender_id": str(second_person.id),
        "message": "Hoi!",
    }
    resp = await client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 200

    # Sender (second_person) should see the DM root in their inbox
    resp = await client.get(
        "/api/notifications",
        params={"person_id": str(second_person.id)},
    )
    assert resp.status_code == 200
    items = resp.json()
    dm_items = [i for i in items if i["type"] == "direct_message"]
    assert len(dm_items) >= 1
    assert any(i["message"] == "Hoi!" for i in dm_items)


async def test_dm_sender_unread_count_unchanged_recipient_increases(
    client, sample_person, second_person
):
    """Sender's root is pre-read so their unread count stays the same.

    The *recipient's* unread count should increase by 1.
    """
    # Baseline counts
    resp = await client.get(
        "/api/notifications/count",
        params={"person_id": str(second_person.id)},
    )
    sender_baseline = resp.json()["count"]

    resp = await client.get(
        "/api/notifications/count",
        params={"person_id": str(sample_person.id)},
    )
    recipient_baseline = resp.json()["count"]

    # second_person sends DM to sample_person
    payload = {
        "person_id": str(sample_person.id),
        "sender_id": str(second_person.id),
        "message": "Test bericht",
    }
    await client.post("/api/notifications/send", json=payload)

    # Sender's unread count should NOT increase (sender root is pre-read)
    resp = await client.get(
        "/api/notifications/count",
        params={"person_id": str(second_person.id)},
    )
    assert resp.json()["count"] == sender_baseline

    # Recipient's unread count should increase
    resp = await client.get(
        "/api/notifications/count",
        params={"person_id": str(sample_person.id)},
    )
    assert resp.json()["count"] == recipient_baseline + 1


async def test_dm_sender_sees_root_as_read_recipient_as_unread(
    client, sample_person, second_person
):
    """DM root appears read for sender, unread for recipient in list endpoint."""
    # second_person sends DM to sample_person
    payload = {
        "person_id": str(sample_person.id),
        "sender_id": str(second_person.id),
        "message": "Hallo!",
    }
    resp = await client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 200
    sender_root_id = resp.json()["id"]

    # Sender (second_person) sees their root as read
    resp = await client.get(
        "/api/notifications",
        params={"person_id": str(second_person.id)},
    )
    dm_for_sender = next((i for i in resp.json() if i["id"] == sender_root_id), None)
    assert dm_for_sender is not None
    assert dm_for_sender["is_read"] is True

    # Recipient (sample_person) has their own root which is unread
    resp = await client.get(
        "/api/notifications",
        params={"person_id": str(sample_person.id)},
    )
    dm_for_recipient = next(
        (i for i in resp.json() if i["type"] == "direct_message" and not i["is_read"]),
        None,
    )
    assert dm_for_recipient is not None
    assert dm_for_recipient["message"] == "Hallo!"


async def test_reply_re_marks_root_unread_and_sender_still_sees_read(
    client, sample_person, second_person
):
    """After a reply, recipient root becomes unread; sender root stays read."""
    # second_person sends DM to sample_person
    send_resp = await client.post(
        "/api/notifications/send",
        json={
            "person_id": str(sample_person.id),
            "sender_id": str(second_person.id),
            "message": "Eerste bericht",
        },
    )
    sender_root_id = send_resp.json()["id"]

    # Find recipient's root
    resp = await client.get(
        "/api/notifications",
        params={"person_id": str(sample_person.id)},
    )
    recipient_root = next(
        i
        for i in resp.json()
        if i["type"] == "direct_message" and i["message"] == "Eerste bericht"
    )
    recipient_root_id = recipient_root["id"]

    # Recipient marks it read
    await client.put(f"/api/notifications/{recipient_root_id}/read")

    # Sender replies (via their own root)
    await client.post(
        f"/api/notifications/{sender_root_id}/reply",
        json={
            "sender_id": str(second_person.id),
            "message": "Nog iets",
        },
    )

    # Recipient root should be unread again
    resp = await client.get(f"/api/notifications/{recipient_root_id}")
    assert resp.json()["is_read"] is False

    # Sender root still read
    resp = await client.get(f"/api/notifications/{sender_root_id}")
    assert resp.json()["is_read"] is True


# ---------------------------------------------------------------------------
# Reply to notification
# ---------------------------------------------------------------------------


async def test_reply_to_notification(
    client, sample_person, second_person, sample_notification
):
    """POST /api/notifications/{id}/reply creates a reply in the thread."""
    payload = {
        "sender_id": str(sample_person.id),
        "message": "Dit is een reactie!",
    }
    resp = await client.post(
        f"/api/notifications/{sample_notification.id}/reply", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "direct_message"
    assert data["parent_id"] == str(sample_notification.id)
    assert data["message"] == "Dit is een reactie!"
    assert "Reactie van" in data["title"]


async def test_reply_to_notification_not_found(client, sample_person):
    """POST /api/notifications/{id}/reply returns 404 for non-existent parent."""
    fake_id = uuid.uuid4()
    payload = {
        "sender_id": str(sample_person.id),
        "message": "Reactie op niks",
    }
    resp = await client.post(f"/api/notifications/{fake_id}/reply", json=payload)
    assert resp.status_code == 404


async def test_reply_threads_to_root(
    client, db_session, sample_person, second_person, sample_notification
):
    """Replying to a reply threads up to the root parent."""
    from bouwmeester.models.notification import Notification

    # Create a first reply
    first_reply = Notification(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        type="direct_message",
        title="Eerste reactie",
        message="Reactie 1",
        sender_id=sample_person.id,
        parent_id=sample_notification.id,
        is_read=False,
    )
    db_session.add(first_reply)
    await db_session.flush()

    # Reply to the reply - should thread to root
    payload = {
        "sender_id": str(second_person.id),
        "message": "Reactie op reactie",
    }
    resp = await client.post(f"/api/notifications/{first_reply.id}/reply", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Should be threaded to root, not to the first reply
    assert data["parent_id"] == str(sample_notification.id)


# ---------------------------------------------------------------------------
# Get replies
# ---------------------------------------------------------------------------


async def test_get_replies(
    client, db_session, sample_person, second_person, sample_notification
):
    """GET /api/notifications/{id}/replies returns thread replies."""
    from bouwmeester.models.notification import Notification

    reply = Notification(
        id=uuid.uuid4(),
        person_id=sample_person.id,
        type="direct_message",
        title="Een reactie",
        message="Reactie tekst",
        sender_id=sample_person.id,
        parent_id=sample_notification.id,
        is_read=False,
    )
    db_session.add(reply)
    await db_session.flush()

    resp = await client.get(f"/api/notifications/{sample_notification.id}/replies")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    ids = {r["id"] for r in data}
    assert str(reply.id) in ids
    # Replies should also have sender_name enriched
    enriched = next(r for r in data if r["id"] == str(reply.id))
    assert enriched["sender_name"] == "Jan Tester"


async def test_get_replies_not_found(client):
    """GET /api/notifications/{id}/replies returns 404 for non-existent parent."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/notifications/{fake_id}/replies")
    assert resp.status_code == 404


async def test_reply_marks_root_unread_for_recipient(
    client, sample_person, second_person
):
    """Replying to a thread marks the other party's root as unread."""
    # Create a DM thread via the API (so thread_id is set correctly)
    send_resp = await client.post(
        "/api/notifications/send",
        json={
            "person_id": str(sample_person.id),
            "sender_id": str(second_person.id),
            "message": "Start thread",
        },
    )
    assert send_resp.status_code == 200
    sender_root_id = send_resp.json()["id"]

    # Find recipient's root
    resp = await client.get(
        "/api/notifications",
        params={"person_id": str(sample_person.id)},
    )
    recipient_root = next(
        i
        for i in resp.json()
        if i["type"] == "direct_message" and i["message"] == "Start thread"
    )
    recipient_root_id = recipient_root["id"]

    # Mark recipient's root as read
    resp = await client.put(f"/api/notifications/{recipient_root_id}/read")
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True

    # Recipient replies (sample_person)
    resp = await client.post(
        f"/api/notifications/{recipient_root_id}/reply",
        json={
            "sender_id": str(sample_person.id),
            "message": "Antwoord!",
        },
    )
    assert resp.status_code == 200

    # Sender's root should now be unread (they got a reply)
    resp = await client.get(f"/api/notifications/{sender_root_id}")
    assert resp.status_code == 200
    assert resp.json()["is_read"] is False


async def test_list_notifications_includes_reply_count(
    client, db_session, sample_person, second_person, sample_notification
):
    """List notifications includes reply_count from batch enrichment."""
    from bouwmeester.models.notification import Notification

    for i in range(3):
        reply = Notification(
            id=uuid.uuid4(),
            person_id=sample_person.id,
            type="direct_message",
            title=f"Reactie {i}",
            message=f"Reactie {i}",
            sender_id=second_person.id,
            parent_id=sample_notification.id,
            is_read=False,
        )
        db_session.add(reply)
    await db_session.flush()

    resp = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    assert resp.status_code == 200
    data = resp.json()
    notif = next(n for n in data if n["id"] == str(sample_notification.id))
    assert notif["reply_count"] == 3


# ---------------------------------------------------------------------------
# Task creation triggers
# ---------------------------------------------------------------------------


async def test_create_task_notifies_assignee(client, sample_node, second_person):
    """POST /api/tasks with assignee → assignee gets task_assigned notification."""
    payload = {
        "title": "Nieuwe taak voor assignee",
        "node_id": str(sample_node.id),
        "assignee_id": str(second_person.id),
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 201

    # Check notifications for the assignee
    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    task_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(task_notifs) >= 1
    assert any("Nieuwe taak" in n["title"] for n in task_notifs)


async def test_create_task_with_org_unit_notifies_manager(
    client, sample_node, sample_person, org_with_manager, third_person
):
    """POST /api/tasks with org unit → manager gets notification."""
    payload = {
        "title": "Eenheidstaak",
        "node_id": str(sample_node.id),
        "assignee_id": str(sample_person.id),
        "organisatie_eenheid_id": str(org_with_manager.id),
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 201

    # Check notifications for the manager (third_person)
    notifs = await client.get(
        "/api/notifications", params={"person_id": str(third_person.id)}
    )
    data = notifs.json()
    task_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(task_notifs) >= 1
    assert any("eenheid" in n["title"].lower() for n in task_notifs)


# ---------------------------------------------------------------------------
# Task update triggers
# ---------------------------------------------------------------------------


async def test_update_task_reassignment_notifies_both(
    client, sample_task, sample_person, second_person
):
    """Change assignee → old gets task_reassigned, new gets task_assigned."""
    payload = {"assignee_id": str(second_person.id)}
    resp = await client.put(f"/api/tasks/{sample_task.id}", json=payload)
    assert resp.status_code == 200

    # Old assignee (sample_person) gets task_reassigned
    notifs = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    data = notifs.json()
    reassign_notifs = [n for n in data if n["type"] == "task_reassigned"]
    assert len(reassign_notifs) >= 1

    # New assignee (second_person) gets task_assigned
    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    assign_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(assign_notifs) >= 1


async def test_update_task_first_assignment_notifies_new(
    client, db_session, sample_node, second_person
):
    """Set assignee on unassigned task → new gets task_assigned (no reassign)."""
    from bouwmeester.models.task import Task

    task = Task(
        id=uuid.uuid4(),
        title="Unassigned taak",
        node_id=sample_node.id,
        assignee_id=None,
        status="open",
        priority="normaal",
    )
    db_session.add(task)
    await db_session.flush()

    payload = {"assignee_id": str(second_person.id)}
    resp = await client.put(f"/api/tasks/{task.id}", json=payload)
    assert resp.status_code == 200

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    assign_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(assign_notifs) >= 1
    # No task_reassigned should exist (nobody was assigned before)
    reassign_notifs = [n for n in data if n["type"] == "task_reassigned"]
    assert len(reassign_notifs) == 0


async def test_update_task_completion_notifies_stakeholders(
    client, db_session, sample_task, sample_node, second_person
):
    """Status → done → stakeholders get task_completed."""
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    # Add second_person as stakeholder
    sh = NodeStakeholder(
        node_id=sample_node.id,
        person_id=second_person.id,
        rol="betrokken",
    )
    db_session.add(sh)
    await db_session.flush()

    payload = {"status": "done"}
    resp = await client.put(f"/api/tasks/{sample_task.id}", json=payload)
    assert resp.status_code == 200

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    completed_notifs = [n for n in data if n["type"] == "task_completed"]
    assert len(completed_notifs) >= 1


async def test_update_task_org_unit_change_notifies_manager(
    client, sample_task, org_with_manager, third_person
):
    """Change org unit → new manager notified."""
    payload = {"organisatie_eenheid_id": str(org_with_manager.id)}
    resp = await client.put(f"/api/tasks/{sample_task.id}", json=payload)
    assert resp.status_code == 200

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(third_person.id)}
    )
    data = notifs.json()
    unit_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(unit_notifs) >= 1


# ---------------------------------------------------------------------------
# Edge creation
# ---------------------------------------------------------------------------


async def test_create_edge_notifies_stakeholders(
    client, db_session, sample_node, second_node, sample_edge_type, sample_person
):
    """Stakeholders of both nodes get edge_created."""
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    sh = NodeStakeholder(
        node_id=sample_node.id,
        person_id=sample_person.id,
        rol="eigenaar",
    )
    db_session.add(sh)
    await db_session.flush()

    payload = {
        "from_node_id": str(sample_node.id),
        "to_node_id": str(second_node.id),
        "edge_type_id": sample_edge_type.id,
    }
    resp = await client.post("/api/edges", json=payload)
    assert resp.status_code == 201

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    data = notifs.json()
    edge_notifs = [n for n in data if n["type"] == "edge_created"]
    assert len(edge_notifs) >= 1


async def test_create_edge_deduplicates(
    client, db_session, sample_node, second_node, sample_edge_type, sample_person
):
    """Person on both nodes → only 1 notification."""
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    # Add same person as stakeholder on both nodes
    for node in [sample_node, second_node]:
        sh = NodeStakeholder(
            node_id=node.id,
            person_id=sample_person.id,
            rol="eigenaar",
        )
        db_session.add(sh)
    await db_session.flush()

    payload = {
        "from_node_id": str(sample_node.id),
        "to_node_id": str(second_node.id),
        "edge_type_id": sample_edge_type.id,
    }
    resp = await client.post("/api/edges", json=payload)
    assert resp.status_code == 201

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(sample_person.id)}
    )
    data = notifs.json()
    edge_notifs = [n for n in data if n["type"] == "edge_created"]
    assert len(edge_notifs) == 1


# ---------------------------------------------------------------------------
# Stakeholder triggers
# ---------------------------------------------------------------------------


async def test_add_stakeholder_notifies_person(client, sample_node, second_person):
    """Adding a stakeholder notifies the person."""
    payload = {
        "person_id": str(second_person.id),
        "rol": "betrokken",
    }
    resp = await client.post(f"/api/nodes/{sample_node.id}/stakeholders", json=payload)
    assert resp.status_code == 201

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    sh_notifs = [n for n in data if n["type"] == "stakeholder_added"]
    assert len(sh_notifs) >= 1
    assert any("betrokken" in n["title"] for n in sh_notifs)


async def test_update_stakeholder_role_notifies_person(
    client, db_session, sample_node, second_person
):
    """Changing role notifies the person."""
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    sh = NodeStakeholder(
        node_id=sample_node.id,
        person_id=second_person.id,
        rol="betrokken",
    )
    db_session.add(sh)
    await db_session.flush()

    payload = {"rol": "eigenaar"}
    resp = await client.put(
        f"/api/nodes/{sample_node.id}/stakeholders/{sh.id}", json=payload
    )
    assert resp.status_code == 200

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    role_notifs = [n for n in data if n["type"] == "stakeholder_role_changed"]
    assert len(role_notifs) >= 1


async def test_update_stakeholder_same_role_no_notification(
    client, db_session, sample_node, second_person
):
    """Same role → no stakeholder_role_changed notification."""
    from bouwmeester.models.node_stakeholder import NodeStakeholder

    sh = NodeStakeholder(
        node_id=sample_node.id,
        person_id=second_person.id,
        rol="betrokken",
    )
    db_session.add(sh)
    await db_session.flush()

    payload = {"rol": "betrokken"}
    resp = await client.put(
        f"/api/nodes/{sample_node.id}/stakeholders/{sh.id}", json=payload
    )
    assert resp.status_code == 200

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(second_person.id)}
    )
    data = notifs.json()
    role_notifs = [n for n in data if n["type"] == "stakeholder_role_changed"]
    assert len(role_notifs) == 0


# ---------------------------------------------------------------------------
# Manager notifications
# ---------------------------------------------------------------------------


async def test_manager_not_notified_when_also_assignee(
    client, sample_node, org_with_manager, third_person
):
    """Manager is also assignee → no duplicate notification."""
    payload = {
        "title": "Manager self-assign",
        "node_id": str(sample_node.id),
        "assignee_id": str(third_person.id),
        "organisatie_eenheid_id": str(org_with_manager.id),
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 201

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(third_person.id)}
    )
    data = notifs.json()
    # Should have exactly 1 task_assigned (from direct assignment),
    # NOT a second one from manager notification
    task_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(task_notifs) == 1


async def test_manager_fallback_to_legacy(
    client, sample_node, sample_person, org_with_legacy_manager, third_person
):
    """No temporal record → uses legacy manager_id."""
    payload = {
        "title": "Legacy manager taak",
        "node_id": str(sample_node.id),
        "assignee_id": str(sample_person.id),
        "organisatie_eenheid_id": str(org_with_legacy_manager.id),
    }
    resp = await client.post("/api/tasks", json=payload)
    assert resp.status_code == 201

    notifs = await client.get(
        "/api/notifications", params={"person_id": str(third_person.id)}
    )
    data = notifs.json()
    task_notifs = [n for n in data if n["type"] == "task_assigned"]
    assert len(task_notifs) >= 1


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


async def test_dashboard_stats_returns_counts(
    client, db_session, sample_person, sample_node
):
    """GET /api/notifications/dashboard-stats returns correct counts."""
    from bouwmeester.models.task import Task

    # Create an open task assigned to sample_person
    task = Task(
        id=uuid.uuid4(),
        title="Open taak",
        node_id=sample_node.id,
        assignee_id=sample_person.id,
        status="open",
        priority="normaal",
        deadline=date.today() + timedelta(days=7),
    )
    db_session.add(task)
    await db_session.flush()

    resp = await client.get(
        "/api/notifications/dashboard-stats",
        params={"person_id": str(sample_person.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["corpus_node_count"] >= 1
    assert data["open_task_count"] >= 1
    assert data["overdue_task_count"] >= 0


async def test_dashboard_stats_overdue_excludes_done(
    client, db_session, sample_person, sample_node
):
    """Done tasks are not counted as overdue."""
    from bouwmeester.models.task import Task

    # Create an overdue but done task
    task = Task(
        id=uuid.uuid4(),
        title="Done overdue taak",
        node_id=sample_node.id,
        assignee_id=sample_person.id,
        status="done",
        priority="normaal",
        deadline=date.today() - timedelta(days=7),
    )
    db_session.add(task)
    await db_session.flush()

    resp = await client.get(
        "/api/notifications/dashboard-stats",
        params={"person_id": str(sample_person.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    # The done task should not count as overdue
    assert data["overdue_task_count"] == 0


# ---------------------------------------------------------------------------
# Sender spoofing prevention
# ---------------------------------------------------------------------------


@pytest.fixture
async def authenticated_client(db_session, second_person):
    """Client where get_optional_user returns second_person (simulating auth)."""
    from bouwmeester.core.app import create_app
    from tests.conftest import InMemorySessionStore

    app = create_app()

    async def _override_get_db():
        yield db_session

    async def _override_get_optional_user():
        return second_person

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = _override_get_optional_user

    mem_store = InMemorySessionStore()
    app.state.session_store = mem_store
    for mw in app.user_middleware:
        if hasattr(mw, "kwargs") and "store" in mw.kwargs:
            mw.kwargs["store"] = mem_store

    app.middleware_stack = app.build_middleware_stack()

    csrf = {"token": ""}

    async def _inject_csrf(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and csrf["token"]:
            request.headers["X-CSRF-Token"] = csrf["token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        event_hooks={"request": [_inject_csrf]},
    ) as ac:
        init_resp = await ac.get("/api/auth/status")
        for cookie_header in init_resp.headers.get_list("set-cookie"):
            if cookie_header.startswith("bm_csrf="):
                csrf["token"] = cookie_header.split("=", 1)[1].split(";")[0]
                break
        yield ac

    app.dependency_overrides.clear()


async def test_send_message_spoofing_rejected(
    authenticated_client, sample_person, second_person
):
    """POST /api/notifications/send rejects sender_id != authenticated user."""
    # authenticated_client is logged in as second_person.
    # Try sending a message with sample_person as sender → spoofing.
    payload = {
        "person_id": str(second_person.id),
        "sender_id": str(sample_person.id),  # Not the authenticated user
        "message": "Spoofed bericht",
    }
    resp = await authenticated_client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 403
    assert "Sender" in resp.json()["detail"]


async def test_send_message_allowed_when_sender_matches(
    authenticated_client, sample_person, second_person
):
    """POST /api/notifications/send succeeds when sender_id matches auth user."""
    # authenticated_client is logged in as second_person.
    # Send with second_person as sender → valid.
    payload = {
        "person_id": str(sample_person.id),
        "sender_id": str(second_person.id),
        "message": "Legit bericht",
    }
    resp = await authenticated_client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 200


async def test_reply_spoofing_rejected(
    authenticated_client, sample_person, second_person, sample_notification
):
    """POST /api/notifications/{id}/reply rejects sender_id != auth user."""
    # authenticated_client is logged in as second_person.
    # Try replying with sample_person as sender → spoofing.
    payload = {
        "sender_id": str(sample_person.id),  # Not the authenticated user
        "message": "Spoofed reactie",
    }
    resp = await authenticated_client.post(
        f"/api/notifications/{sample_notification.id}/reply", json=payload
    )
    assert resp.status_code == 403
    assert "Sender" in resp.json()["detail"]


async def test_reply_allowed_when_sender_matches(
    authenticated_client, sample_person, second_person, sample_notification
):
    """POST /api/notifications/{id}/reply succeeds when sender matches auth."""
    # authenticated_client is logged in as second_person.
    payload = {
        "sender_id": str(second_person.id),
        "message": "Legit reactie",
    }
    resp = await authenticated_client.post(
        f"/api/notifications/{sample_notification.id}/reply", json=payload
    )
    assert resp.status_code == 200
