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
