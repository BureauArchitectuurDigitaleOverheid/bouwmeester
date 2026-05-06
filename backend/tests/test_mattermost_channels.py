"""Tests voor MattermostChannelLink routes en skeleton-ingest."""

import uuid

import pytest

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    SCOPE_LEAD,
    MattermostChannelLink,
)
from bouwmeester.models.mattermost_post_link import MattermostPostLink


def _channel_id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def sample_initiatief(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="Test initiatief")
    db_session.add(init)
    await db_session.flush()
    return init


@pytest.fixture
async def sample_lead(db_session, sample_initiatief):
    lead = Lead(
        id=uuid.uuid4(),
        title="Test lead",
        stage="inbox",
        initiatief_id=sample_initiatief.id,
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def test_create_initiatief_channel_link(client, sample_initiatief):
    cid = _channel_id()
    resp = await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json={
            "channel_id": cid,
            "channel_name": "test-kanaal",
            "channel_display_name": "Test kanaal",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["channel_id"] == cid
    assert body["scope_type"] == SCOPE_INITIATIEF
    assert body["scope_id"] == str(sample_initiatief.id)
    # Initiatief-default: suggest leads aan, auto-note uit.
    assert body["suggest_leads_enabled"] is True
    assert body["auto_note_enabled"] is False


async def test_create_lead_channel_link(client, sample_lead):
    cid = _channel_id()
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/mattermost-channels",
        json={
            "channel_id": cid,
            "channel_name": "project-kanaal",
            "channel_display_name": "Project kanaal",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["scope_type"] == SCOPE_LEAD
    # Lead-default: auto-note aan, suggest leads uit.
    assert body["auto_note_enabled"] is True
    assert body["suggest_leads_enabled"] is False


async def test_cannot_link_same_channel_twice(client, sample_initiatief):
    cid = _channel_id()
    payload = {
        "channel_id": cid,
        "channel_name": "kanaal",
        "channel_display_name": "Kanaal",
    }
    first = await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json=payload,
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json=payload,
    )
    assert second.status_code == 409


async def test_list_channels_for_initiatief(client, sample_initiatief):
    cid = _channel_id()
    await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json={
            "channel_id": cid,
            "channel_name": "kanaal",
            "channel_display_name": "Kanaal",
        },
    )
    resp = await client.get(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels"
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["channel_id"] == cid


async def test_update_channel_settings(client, sample_initiatief):
    cid = _channel_id()
    create = await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json={
            "channel_id": cid,
            "channel_name": "kanaal",
            "channel_display_name": "Kanaal",
        },
    )
    link_id = create.json()["id"]
    resp = await client.patch(
        f"/api/mattermost-channels/{link_id}",
        json={"auto_note_enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json()["auto_note_enabled"] is True


async def test_delete_channel_link(client, sample_initiatief):
    cid = _channel_id()
    create = await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json={
            "channel_id": cid,
            "channel_name": "kanaal",
            "channel_display_name": "Kanaal",
        },
    )
    link_id = create.json()["id"]
    resp = await client.delete(f"/api/mattermost-channels/{link_id}")
    assert resp.status_code == 204
    after = await client.get(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels"
    )
    assert after.json() == []


async def test_create_initiatief_channel_invalid_id(client, sample_initiatief):
    resp = await client.post(
        f"/api/initiatieven/{sample_initiatief.id}/mattermost-channels",
        json={
            "channel_id": "not-a-mm-id",
            "channel_name": "x",
            "channel_display_name": "X",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Skeleton-ingest (websocket-service zonder echte websocket)
# ---------------------------------------------------------------------------


async def test_record_post_writes_post_link(db_session, sample_initiatief):
    """Skeleton-`_record_post` legt een post vast voor een gekoppeld kanaal."""
    from bouwmeester.services.mattermost_websocket_service import (
        MattermostWebsocketService,
    )

    cid = _channel_id()
    link = MattermostChannelLink(
        channel_id=cid,
        channel_name="k",
        channel_display_name="K",
        scope_type=SCOPE_INITIATIEF,
        scope_id=sample_initiatief.id,
        auto_note_enabled=False,
        suggest_leads_enabled=True,
    )
    db_session.add(link)
    await db_session.flush()

    service = MattermostWebsocketService()
    post = {
        "id": "p" + uuid.uuid4().hex[:25],
        "channel_id": cid,
        "user_id": "u" + uuid.uuid4().hex[:25],
        "create_at": 1_700_000_000_000,
    }
    await service._record_post(db_session, post)

    from sqlalchemy import select

    result = await db_session.execute(
        select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
    )
    record = result.scalar_one()
    assert record.channel_id == cid
    assert record.scope_type == SCOPE_INITIATIEF
    assert record.scope_id == sample_initiatief.id


async def test_record_post_idempotent(db_session, sample_initiatief):
    """Tweede keer dezelfde post → geen tweede record."""
    from sqlalchemy import select

    from bouwmeester.services.mattermost_websocket_service import (
        MattermostWebsocketService,
    )

    cid = _channel_id()
    link = MattermostChannelLink(
        channel_id=cid,
        channel_name="k",
        channel_display_name="K",
        scope_type=SCOPE_INITIATIEF,
        scope_id=sample_initiatief.id,
    )
    db_session.add(link)
    await db_session.flush()

    service = MattermostWebsocketService()
    post = {
        "id": "p" + uuid.uuid4().hex[:25],
        "channel_id": cid,
        "user_id": "u" + uuid.uuid4().hex[:25],
        "create_at": 1_700_000_000_000,
    }
    await service._record_post(db_session, post)
    await service._record_post(db_session, post)

    result = await db_session.execute(
        select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
    )
    rows = list(result.scalars().all())
    assert len(rows) == 1


async def test_record_post_skips_unlinked_channel(db_session):
    """Posts in een niet-gekoppeld kanaal worden niet vastgelegd."""
    from sqlalchemy import select

    from bouwmeester.services.mattermost_websocket_service import (
        MattermostWebsocketService,
    )

    service = MattermostWebsocketService()
    post = {
        "id": "p" + uuid.uuid4().hex[:25],
        "channel_id": _channel_id(),
        "user_id": "u" + uuid.uuid4().hex[:25],
        "create_at": 1_700_000_000_000,
    }
    await service._record_post(db_session, post)

    result = await db_session.execute(
        select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
    )
    assert result.scalar_one_or_none() is None


async def test_record_post_skips_bot_self(db_session, sample_initiatief):
    """Bot's eigen posts worden niet ingelezen (anti feedback-loop)."""
    from sqlalchemy import select

    from bouwmeester.services.mattermost_websocket_service import (
        MattermostWebsocketService,
    )

    cid = _channel_id()
    link = MattermostChannelLink(
        channel_id=cid,
        channel_name="k",
        channel_display_name="K",
        scope_type=SCOPE_INITIATIEF,
        scope_id=sample_initiatief.id,
    )
    db_session.add(link)
    await db_session.flush()

    bot_id = "b" + uuid.uuid4().hex[:25]
    service = MattermostWebsocketService()
    service._bot_user_id = bot_id

    post = {
        "id": "p" + uuid.uuid4().hex[:25],
        "channel_id": cid,
        "user_id": bot_id,
        "create_at": 1_700_000_000_000,
    }
    await service._record_post(db_session, post)
    result = await db_session.execute(
        select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
    )
    assert result.scalar_one_or_none() is None
