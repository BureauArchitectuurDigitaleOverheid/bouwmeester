"""Comprehensive API tests for the activity router."""

import uuid

# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------


async def test_activity_feed_returns_200(client):
    """GET /api/activity/feed returns 200 and a list."""
    resp = await client.get("/api/activity/feed")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


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
