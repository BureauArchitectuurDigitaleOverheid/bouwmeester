"""Comprehensive API tests for the notifications router."""

import uuid

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
    """POST /api/notifications/send creates a direct message notification."""
    payload = {
        "person_id": str(sample_person.id),
        "sender_id": str(second_person.id),
        "message": "Hallo, dit is een testbericht!",
    }
    resp = await client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["person_id"] == str(sample_person.id)
    assert data["type"] == "direct_message"
    assert "Bericht van" in data["title"]


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
