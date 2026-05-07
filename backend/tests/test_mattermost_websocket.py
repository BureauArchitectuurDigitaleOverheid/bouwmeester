"""Tests voor de WS-dispatcher: user_removed / channel_deleted → disabled_at."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.services.mattermost_service import (
    MattermostService,
    MattermostUnavailableError,
)
from bouwmeester.services.mattermost_websocket_service import (
    MattermostWebsocketService,
    _ws_url_from_http,
    disable_channel_link,
)


class TestWsUrlFromHttp:
    """The ws-URL builder must preserve any sub-path on the Mattermost host."""

    def test_root_install(self):
        assert (
            _ws_url_from_http("https://mm.example.com")
            == "wss://mm.example.com/api/v4/websocket"
        )

    def test_root_install_with_trailing_slash(self):
        assert (
            _ws_url_from_http("https://mm.example.com/")
            == "wss://mm.example.com/api/v4/websocket"
        )

    def test_subpath_install(self):
        # Mattermost achter reverse-proxy op /chat — het pad moet meegaan,
        # anders krijgen we HTTP 404 van de proxy.
        assert (
            _ws_url_from_http("https://digilab.overheid.nl/chat")
            == "wss://digilab.overheid.nl/chat/api/v4/websocket"
        )

    def test_subpath_install_with_trailing_slash(self):
        assert (
            _ws_url_from_http("https://digilab.overheid.nl/chat/")
            == "wss://digilab.overheid.nl/chat/api/v4/websocket"
        )

    def test_http_becomes_ws(self):
        assert (
            _ws_url_from_http("http://localhost:8065")
            == "ws://localhost:8065/api/v4/websocket"
        )


def _id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def linked_channel(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="Test")
    db_session.add(init)
    await db_session.flush()
    cid = _id()
    link = MattermostChannelLink(
        channel_id=cid,
        channel_name="x",
        channel_display_name="X",
        scope_type=SCOPE_INITIATIEF,
        scope_id=init.id,
    )
    db_session.add(link)
    await db_session.flush()
    return link


# ---------------------------------------------------------------------------
# disable_channel_link helper
# ---------------------------------------------------------------------------


async def test_disable_channel_link_sets_disabled_at(db_session, linked_channel):
    ok = await disable_channel_link(db_session, linked_channel.channel_id)
    assert ok is True
    await db_session.refresh(linked_channel)
    assert linked_channel.disabled_at is not None


async def test_disable_channel_link_idempotent(db_session, linked_channel):
    await disable_channel_link(db_session, linked_channel.channel_id)
    first = linked_channel.disabled_at
    ok = await disable_channel_link(db_session, linked_channel.channel_id)
    assert ok is False
    await db_session.refresh(linked_channel)
    assert linked_channel.disabled_at == first


async def test_disable_channel_link_unknown_channel(db_session):
    ok = await disable_channel_link(db_session, _id())
    assert ok is False


# ---------------------------------------------------------------------------
# _channel_lost_channel_id parsing
# ---------------------------------------------------------------------------


def test_channel_lost_user_removed_other_user_ignored():
    svc = MattermostWebsocketService()
    svc._bot_user_id = "bot1234567890123456789012a"
    msg = {
        "event": "user_removed",
        "data": {"user_id": "someone_else_____________a", "channel_id": _id()},
    }
    assert svc._channel_lost_channel_id("user_removed", msg) is None


def test_channel_lost_user_removed_bot_data_payload():
    svc = MattermostWebsocketService()
    svc._bot_user_id = "bot1234567890123456789012a"
    cid = _id()
    msg = {
        "event": "user_removed",
        "data": {"user_id": svc._bot_user_id, "channel_id": cid},
    }
    assert svc._channel_lost_channel_id("user_removed", msg) == cid


def test_channel_lost_user_removed_bot_broadcast_payload():
    svc = MattermostWebsocketService()
    svc._bot_user_id = "bot1234567890123456789012a"
    cid = _id()
    msg = {
        "event": "user_removed",
        "data": {"user_id": svc._bot_user_id},
        "broadcast": {"channel_id": cid},
    }
    assert svc._channel_lost_channel_id("user_removed", msg) == cid


def test_channel_lost_channel_deleted_data_payload():
    svc = MattermostWebsocketService()
    cid = _id()
    msg = {"event": "channel_deleted", "data": {"channel_id": cid}}
    assert svc._channel_lost_channel_id("channel_deleted", msg) == cid


def test_channel_lost_channel_deleted_nested_channel_object():
    svc = MattermostWebsocketService()
    cid = _id()
    msg = {"event": "channel_deleted", "data": {"channel": {"id": cid}}}
    assert svc._channel_lost_channel_id("channel_deleted", msg) == cid


def test_channel_lost_unknown_event():
    svc = MattermostWebsocketService()
    assert svc._channel_lost_channel_id("user_typing", {"data": {}}) is None


# ---------------------------------------------------------------------------
# End-to-end: parse + disable
# ---------------------------------------------------------------------------


async def test_user_removed_for_bot_disables_link(db_session, linked_channel):
    """Combinatie van parsing + DB-write: bot wordt uit kanaal verwijderd
    → ``disabled_at`` wordt gezet."""
    svc = MattermostWebsocketService()
    svc._bot_user_id = "bot1234567890123456789012a"
    msg = {
        "event": "user_removed",
        "data": {
            "user_id": svc._bot_user_id,
            "channel_id": linked_channel.channel_id,
        },
    }
    cid = svc._channel_lost_channel_id("user_removed", msg)
    assert cid == linked_channel.channel_id
    await disable_channel_link(db_session, cid, event="user_removed")
    await db_session.refresh(linked_channel)
    assert linked_channel.disabled_at is not None


async def test_user_removed_for_other_user_keeps_link_active(
    db_session, linked_channel
):
    svc = MattermostWebsocketService()
    svc._bot_user_id = "bot1234567890123456789012a"
    msg = {
        "event": "user_removed",
        "data": {
            "user_id": "anotherperson12345678901a",
            "channel_id": linked_channel.channel_id,
        },
    }
    assert svc._channel_lost_channel_id("user_removed", msg) is None
    await db_session.refresh(linked_channel)
    assert linked_channel.disabled_at is None


# ---------------------------------------------------------------------------
# Race-test: twee parallel approval-clicks zien het lock
# ---------------------------------------------------------------------------


async def test_double_approval_with_real_lock(_test_engine, create_person):
    """Echte race-test: twee parallelle sessions klikken op dezelfde knop.

    Eén krijgt de lock en maakt de Lead, de ander wacht en ziet
    ``status != "pending"``. Resultaat: precies één Lead, één lopende
    SuggestedLead met ``status="approved_new"``.

    We omzeilen de standaard ``db_session``-fixture (die rolt aan het
    eind alles terug en deelt één connectie) en gebruiken daadwerkelijk
    twee concurrent ``AsyncSession``-instanties op dezelfde engine.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    from bouwmeester.models.lead import Lead
    from bouwmeester.models.mattermost_user import MattermostUser
    from bouwmeester.models.resource_permission import ResourcePermission
    from bouwmeester.models.suggested_lead import SuggestedLead
    from bouwmeester.services.mattermost_slash_service import MattermostSlashService

    init_id = uuid.uuid4()
    sug_id = uuid.uuid4()
    person_id = uuid.uuid4()
    mm_uid = _id()
    cid = _id()

    # Setup: één persoon met permission, één SuggestedLead in pending.
    async with AsyncSession(_test_engine, expire_on_commit=False) as setup:
        from bouwmeester.models.person import Person
        from bouwmeester.models.person_email import PersonEmail

        setup.add(Initiatief(id=init_id, naam="Race"))
        await setup.flush()
        setup.add(
            Person(
                id=person_id,
                naam="A Race",
                email="race@example.com",
                is_active=True,
            )
        )
        await setup.flush()
        setup.add(
            PersonEmail(person_id=person_id, email="race@example.com", is_default=True)
        )
        setup.add(
            MattermostUser(
                person_id=person_id,
                mattermost_user_id=mm_uid,
                mattermost_username="a",
            )
        )
        setup.add(
            ResourcePermission(
                person_id=person_id,
                resource_type="initiatief",
                resource_id=init_id,
                rol="eigenaar",
            )
        )
        setup.add(
            SuggestedLead(
                id=sug_id,
                source_post_id=_id(),
                source_channel_id=cid,
                initiatief_id=init_id,
                proposed_title="Race lead",
                raw_text="iets",
                status="pending",
            )
        )
        await setup.commit()

    async def _click() -> dict:
        async with AsyncSession(_test_engine, expire_on_commit=False) as s:
            from unittest.mock import AsyncMock, patch

            with patch(
                "bouwmeester.services.mattermost_slash_service."
                "MattermostSlashService._update_thread_post",
                new=AsyncMock(return_value=None),
            ):
                service = MattermostSlashService(s)
                result = await service.handle_action(
                    mattermost_user_id=mm_uid,
                    action="create_lead_from_suggestion",
                    context={"suggested_lead_id": str(sug_id)},
                )
            await s.commit()
            return result

    try:
        results = await asyncio.gather(_click(), _click())

        async with AsyncSession(_test_engine, expire_on_commit=False) as verify:
            leads = (
                (
                    await verify.execute(
                        select(Lead).where(Lead.initiatief_id == init_id)
                    )
                )
                .scalars()
                .all()
            )
            sug = (
                await verify.execute(
                    select(SuggestedLead).where(SuggestedLead.id == sug_id)
                )
            ).scalar_one()

        # Exact één Lead, ondanks twee parallel clicks.
        assert len(leads) == 1
        assert sug.status == "approved_new"
        assert sug.approved_lead_id == leads[0].id
        # Eén response is een succesmelding, de ander zegt "al verwerkt".
        msgs = sorted(r.get("ephemeral_text", "") for r in results)
        assert "Lead aangemaakt" in msgs[0] or "al verwerkt" in msgs[0]
        assert "Lead aangemaakt" in msgs[1] or "al verwerkt" in msgs[1]
        assert any("Lead aangemaakt" in m for m in msgs)
        assert any("al verwerkt" in m for m in msgs)
    finally:
        # Cleanup: verwijder de race-fixture-data zodat andere tests een
        # schone DB hebben (we hebben buiten de standaard testtransactie
        # geschreven).
        async with AsyncSession(_test_engine, expire_on_commit=False) as cleanup:
            from sqlalchemy import delete

            from bouwmeester.models.lead_activity import LeadActivity

            await cleanup.execute(
                delete(LeadActivity).where(
                    LeadActivity.lead_id.in_(
                        select(Lead.id).where(Lead.initiatief_id == init_id)
                    )
                )
            )
            await cleanup.execute(delete(Lead).where(Lead.initiatief_id == init_id))
            await cleanup.execute(
                delete(SuggestedLead).where(SuggestedLead.id == sug_id)
            )
            await cleanup.execute(
                delete(ResourcePermission).where(
                    ResourcePermission.person_id == person_id
                )
            )
            await cleanup.execute(
                delete(MattermostUser).where(MattermostUser.person_id == person_id)
            )
            from bouwmeester.models.person import Person
            from bouwmeester.models.person_email import PersonEmail

            await cleanup.execute(
                delete(PersonEmail).where(PersonEmail.person_id == person_id)
            )
            await cleanup.execute(delete(Person).where(Person.id == person_id))
            await cleanup.execute(delete(Initiatief).where(Initiatief.id == init_id))
            await cleanup.commit()


# ---------------------------------------------------------------------------
# is_bot_member_of_channel: 200 / 404 / error-onderscheid
# ---------------------------------------------------------------------------


def _mock_transport(status_code: int):
    """Bouw een httpx.AsyncClient die elke request een vaste status returnt."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="http://mock-mattermost",
        headers={"Authorization": "Bearer test"},
    )


async def test_is_bot_member_of_channel_returns_true_on_200(db_session):
    service = MattermostService(db_session)
    with (
        patch.object(
            service,
            "get_bot_user_id",
            new=AsyncMock(return_value="bot-id-26-chars-1234567890"),
        ),
        patch.object(
            service, "_get_client", new=AsyncMock(return_value=_mock_transport(200))
        ),
    ):
        assert await service.is_bot_member_of_channel(_id()) is True


async def test_is_bot_member_of_channel_returns_false_on_404(db_session):
    service = MattermostService(db_session)
    with (
        patch.object(
            service,
            "get_bot_user_id",
            new=AsyncMock(return_value="bot-id-26-chars-1234567890"),
        ),
        patch.object(
            service, "_get_client", new=AsyncMock(return_value=_mock_transport(404))
        ),
    ):
        assert await service.is_bot_member_of_channel(_id()) is False


async def test_is_bot_member_of_channel_raises_on_500(db_session):
    """500 = MM-server-fout. Caller mag dit niet als 'geen lid' interpreteren."""
    service = MattermostService(db_session)
    with (
        patch.object(
            service,
            "get_bot_user_id",
            new=AsyncMock(return_value="bot-id-26-chars-1234567890"),
        ),
        patch.object(
            service, "_get_client", new=AsyncMock(return_value=_mock_transport(500))
        ),
    ):
        with pytest.raises(MattermostUnavailableError):
            await service.is_bot_member_of_channel(_id())


async def test_is_bot_member_of_channel_raises_on_network_error(db_session):
    """Netwerk-glitch = onbekend, niet 'geen lid'."""
    service = MattermostService(db_session)

    def _handler(request):
        raise httpx.ConnectError("connection refused")

    flaky = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="http://mock-mattermost",
    )
    with (
        patch.object(
            service,
            "get_bot_user_id",
            new=AsyncMock(return_value="bot-id-26-chars-1234567890"),
        ),
        patch.object(service, "_get_client", new=AsyncMock(return_value=flaky)),
    ):
        with pytest.raises(MattermostUnavailableError):
            await service.is_bot_member_of_channel(_id())


async def test_is_bot_member_of_channel_raises_when_no_bot_user_id(db_session):
    """Geen bot-user-id beschikbaar = MM niet geconfigureerd / bereikbaar."""
    service = MattermostService(db_session)
    with patch.object(service, "get_bot_user_id", new=AsyncMock(return_value=None)):
        with pytest.raises(MattermostUnavailableError):
            await service.is_bot_member_of_channel(_id())


# ---------------------------------------------------------------------------
# PATCH /api/mattermost-channels/{id} met reenable=true
# ---------------------------------------------------------------------------


async def test_patch_reenable_succeeds_when_bot_is_member(client, linked_channel):
    """Bot is lid (mock 200) → disabled_at wordt None."""
    from datetime import UTC, datetime

    # Eerst link uitschakelen.
    linked_channel.disabled_at = datetime.now(UTC)
    # Mock zowel is_enabled als is_bot_member_of_channel.
    with (
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_bot_member_of_channel",
            new=AsyncMock(return_value=True),
        ),
    ):
        resp = await client.patch(
            f"/api/mattermost-channels/{linked_channel.id}",
            json={"reenable": True},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["disabled_at"] is None


async def test_patch_reenable_409_when_bot_not_member(client, linked_channel):
    """Bot is geen lid (mock 404 → False) → 409 met duidelijke melding."""
    with (
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_bot_member_of_channel",
            new=AsyncMock(return_value=False),
        ),
    ):
        resp = await client.patch(
            f"/api/mattermost-channels/{linked_channel.id}",
            json={"reenable": True},
        )
    assert resp.status_code == 409
    assert "Voeg de bot eerst toe" in resp.json()["detail"]


async def test_patch_reenable_503_on_mm_unavailable(client, linked_channel):
    """Membership-check werpt MattermostUnavailableError → 503."""
    with (
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_bot_member_of_channel",
            new=AsyncMock(side_effect=MattermostUnavailableError("netwerk")),
        ),
    ):
        resp = await client.patch(
            f"/api/mattermost-channels/{linked_channel.id}",
            json={"reenable": True},
        )
    assert resp.status_code == 503
    assert "tijdelijk niet bereikbaar" in resp.json()["detail"]


async def test_patch_reenable_503_when_mm_disabled(client, linked_channel):
    """is_enabled=False → 503 'niet geconfigureerd'."""
    with patch(
        "bouwmeester.services.mattermost_service.MattermostService.is_enabled",
        new=AsyncMock(return_value=False),
    ):
        resp = await client.patch(
            f"/api/mattermost-channels/{linked_channel.id}",
            json={"reenable": True},
        )
    assert resp.status_code == 503
    assert "niet geconfigureerd" in resp.json()["detail"]


async def test_patch_without_reenable_does_not_check_bot(client, linked_channel):
    """Settings-PATCH zonder reenable mag MM niet aanroepen."""
    membership = AsyncMock(return_value=False)
    with (
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.is_bot_member_of_channel",
            new=membership,
        ),
    ):
        resp = await client.patch(
            f"/api/mattermost-channels/{linked_channel.id}",
            json={"auto_note_enabled": True},
        )
    assert resp.status_code == 200
    membership.assert_not_called()


async def test_patch_reenable_false_rejected_by_pydantic(client, linked_channel):
    """Literal[True]: alleen ``true`` of weglaten — false geeft 422."""
    resp = await client.patch(
        f"/api/mattermost-channels/{linked_channel.id}",
        json={"reenable": False},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DM-pad: channel_type uit posted-event + recovery + dedup-cache
# ---------------------------------------------------------------------------


async def test_dispatch_posted_extracts_channel_type():
    """``data.channel_type`` (niet ``post.channel_type``) wordt doorgegeven
    aan ``_record_post`` zodat ``ingest_post`` de DM-flow kan kiezen."""
    import json
    from unittest.mock import AsyncMock, patch

    svc = MattermostWebsocketService()
    captured: dict = {}

    async def fake_record_post(session, post, *, channel_type=None):
        captured["channel_type"] = channel_type
        captured["post_id"] = post.get("id")

    msg = {
        "event": "posted",
        "data": {
            "channel_type": "D",
            "post": json.dumps(
                {"id": "p1", "channel_id": "c1", "user_id": "u1", "message": "hoi"}
            ),
        },
    }
    with patch.object(svc, "_record_post", new=AsyncMock(side_effect=fake_record_post)):
        await svc._dispatch_posted(msg)

    assert captured == {"channel_type": "D", "post_id": "p1"}


async def test_dispatch_posted_with_channel_type_o_falls_through():
    """Open channel (``channel_type='O'``) hoort de oude channel-link-flow
    in te gaan, niet de DM-flow. We verifiëren door te kijken dat
    ``channel_type`` ongewijzigd wordt doorgegeven."""
    import json
    from unittest.mock import AsyncMock, patch

    svc = MattermostWebsocketService()
    captured: dict = {}

    async def fake_record_post(session, post, *, channel_type=None):
        captured["channel_type"] = channel_type

    msg = {
        "event": "posted",
        "data": {
            "channel_type": "O",
            "post": json.dumps(
                {"id": "p2", "channel_id": "c2", "user_id": "u1", "message": "x"}
            ),
        },
    }
    with patch.object(svc, "_record_post", new=AsyncMock(side_effect=fake_record_post)):
        await svc._dispatch_posted(msg)

    assert captured["channel_type"] == "O"


async def test_dispatch_posted_skips_recently_processed_dm():
    """Een DM-post-id die al in de in-memory cache zit, wordt niet opnieuw
    aan ``_record_post`` doorgegeven (race-mitigatie tussen WS-event en
    DM-recovery)."""
    import json
    from unittest.mock import AsyncMock, patch

    svc = MattermostWebsocketService()
    svc._mark_dm_processed("p3")

    record_post = AsyncMock(return_value=None)
    msg = {
        "event": "posted",
        "data": {
            "channel_type": "D",
            "post": json.dumps(
                {"id": "p3", "channel_id": "c1", "user_id": "u1", "message": "BM-x"}
            ),
        },
    }
    with patch.object(svc, "_record_post", new=record_post):
        await svc._dispatch_posted(msg)

    record_post.assert_not_called()


def test_recent_dm_cache_evicts_oldest_over_cap():
    """OrderedDict-cache: bij overflow valt de oudste post-id eruit."""
    from bouwmeester.services.mattermost_websocket_service import (
        _RECENT_DM_CACHE_CAP,
    )

    svc = MattermostWebsocketService()
    for i in range(_RECENT_DM_CACHE_CAP + 5):
        svc._mark_dm_processed(f"post-{i}")

    assert len(svc._recent_dm_post_ids) == _RECENT_DM_CACHE_CAP
    # Oudste 5 zijn weg, jongste 5 zijn er nog.
    assert "post-0" not in svc._recent_dm_post_ids
    assert "post-4" not in svc._recent_dm_post_ids
    assert f"post-{_RECENT_DM_CACHE_CAP + 4}" in svc._recent_dm_post_ids


async def test_recover_dm_posts_uses_cold_start_window_on_first_run():
    """Eerste recovery (``_last_dm_recovery_ms`` is ``None``) moet 2 minuten
    terug kijken via ``get_bot_dm_posts``."""
    from unittest.mock import AsyncMock, MagicMock

    from bouwmeester.services.mattermost_websocket_service import (
        _DM_COLD_START_WINDOW_MS,
    )

    svc = MattermostWebsocketService()
    service = MagicMock()
    service.get_bot_dm_posts = AsyncMock(return_value=[])
    session = MagicMock()

    import time as time_mod

    before = int(time_mod.time() * 1000)
    await svc._recover_dm_posts(session, service)
    after = int(time_mod.time() * 1000)

    service.get_bot_dm_posts.assert_called_once()
    since = service.get_bot_dm_posts.call_args.kwargs["since"]
    # since moet ~2 min vóór nu liggen.
    assert before - _DM_COLD_START_WINDOW_MS - 100 <= since
    assert since <= after - _DM_COLD_START_WINDOW_MS + 100
    # Na recovery is _last_dm_recovery_ms gezet.
    assert svc._last_dm_recovery_ms is not None
    assert before <= svc._last_dm_recovery_ms <= after


async def test_recover_dm_posts_processes_each_post_and_marks_seen():
    """Recovered posts worden doorgegeven aan ``_record_post`` met
    ``channel_type='D'`` en in de dedup-cache gezet."""
    from unittest.mock import AsyncMock, MagicMock, patch

    svc = MattermostWebsocketService()
    service = MagicMock()
    service.get_bot_dm_posts = AsyncMock(
        return_value=[
            {"id": "dm1", "user_id": "u1"},
            {"id": "dm2", "user_id": "u2"},
        ]
    )
    session = MagicMock()

    record_post = AsyncMock(return_value=None)
    with patch.object(svc, "_record_post", new=record_post):
        await svc._recover_dm_posts(session, service)

    assert record_post.await_count == 2
    for call in record_post.call_args_list:
        assert call.kwargs["channel_type"] == "D"
    assert "dm1" in svc._recent_dm_post_ids
    assert "dm2" in svc._recent_dm_post_ids


async def test_recover_dm_posts_skips_already_processed_post():
    """Als een post al in de dedup-cache zit (vroeg WS-event), wordt 'ie
    niet opnieuw verwerkt door de recovery-loop."""
    from unittest.mock import AsyncMock, MagicMock, patch

    svc = MattermostWebsocketService()
    svc._mark_dm_processed("dm-already-seen")

    service = MagicMock()
    service.get_bot_dm_posts = AsyncMock(
        return_value=[
            {"id": "dm-already-seen", "user_id": "u1"},
            {"id": "dm-new", "user_id": "u2"},
        ]
    )
    session = MagicMock()

    record_post = AsyncMock(return_value=None)
    with patch.object(svc, "_record_post", new=record_post):
        await svc._recover_dm_posts(session, service)

    assert record_post.await_count == 1
    posted_ids = [call.args[1]["id"] for call in record_post.call_args_list]
    assert posted_ids == ["dm-new"]


async def test_recover_dm_posts_uses_last_recovery_ms_on_subsequent_runs():
    """Tweede recovery kijkt vanaf ``_last_dm_recovery_ms``, niet vanaf
    de cold-start-window."""
    from unittest.mock import AsyncMock, MagicMock

    svc = MattermostWebsocketService()
    svc._last_dm_recovery_ms = 1_700_000_000_000

    service = MagicMock()
    service.get_bot_dm_posts = AsyncMock(return_value=[])
    session = MagicMock()

    await svc._recover_dm_posts(session, service)

    service.get_bot_dm_posts.assert_called_once()
    assert service.get_bot_dm_posts.call_args.kwargs["since"] == 1_700_000_000_000
