"""Tests for the debates page: the list of what is coming, and starting one.

The route tests stub the TK API and Mattermost at their service boundary
and run against a real database, because the list has to show the channels
that `debat_sessie` knows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from bouwmeester.api.routes import debatten as routes
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.services import debat_kanaal_service as service_mod
from bouwmeester.services.debat_kanaal_service import (
    RETRY_HINT_WEB,
    DebatKanaalService,
    StartOutcome,
)
from bouwmeester.services.mattermost_service import (
    MattermostService,
    MattermostUnavailableError,
)
from bouwmeester.services.tk_activiteit import Activiteit, TkApiError, list_upcoming
from tests.test_debat_kanaal import (
    TEAM,
    FakeMattermost,
    _activiteit,
    _patch_fetch,
    _sessies,
)

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def _row(**overrides) -> dict:
    row = {
        "Id": str(uuid.uuid4()),
        "Nummer": "2026A05428",
        "Soort": "Commissiedebat",
        "Onderwerp": "Leefomgeving",
        "Aanvangstijd": "2026-10-06T16:30:00+02:00",
        "Eindtijd": "2026-10-06T21:30:00+02:00",
        "Status": "Gepland",
        "Voortouwnaam": "vaste commissie voor I&W",
        "Besloten": False,
        "Verwijderd": False,
    }
    row.update(overrides)
    return row


def _client(handler):
    seen: list[httpx.Request] = []

    def recording(request):
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(recording)), seen


@pytest.mark.asyncio
class TestListUpcoming:
    async def test_asks_for_the_window_and_only_public_meetings(self):
        client, seen = _client(lambda r: httpx.Response(200, json={"value": [_row()]}))

        result = await list_upcoming(client, days=21, now=NOW, base_url="http://tk")

        assert [a.onderwerp for a in result] == ["Leefomgeving"]
        params = seen[0].url.params
        # From eight hours back, so a debate that is running is still listed.
        assert "Aanvangstijd ge 2026-10-04T04:00:00Z" in params["$filter"]
        assert "Aanvangstijd lt 2026-10-25T12:00:00Z" in params["$filter"]
        assert "Besloten eq false" in params["$filter"]
        assert "Verwijderd eq false" in params["$filter"]
        assert params["$orderby"] == "Aanvangstijd asc"
        assert params["$top"] == "250"

    async def test_leaves_out_what_cannot_be_listened_to(self):
        rows = [
            _row(Onderwerp="gewoon"),
            _row(Onderwerp="geannuleerd", Status="Geannuleerd"),
            _row(Onderwerp="verplaatst", Status="Verplaatst"),
            # The filter asks for public meetings; a row that slips through
            # is still dropped.
            _row(Onderwerp="besloten", Besloten=True),
            _row(Onderwerp="inbreng", Soort="Inbreng schriftelijk overleg"),
            _row(Onderwerp="zonder id", Id=None),
        ]
        client, _ = _client(lambda r: httpx.Response(200, json={"value": rows}))

        result = await list_upcoming(client, days=21, now=NOW)

        assert [a.onderwerp for a in result] == ["gewoon"]

    async def test_reads_the_next_page_when_one_is_full(self):
        """The API caps a page at 250. A busy month has more."""

        def handler(request):
            skip = int(request.url.params["$skip"])
            size = 250 if skip == 0 else 3
            return httpx.Response(200, json={"value": [_row() for _ in range(size)]})

        client, seen = _client(handler)

        result = await list_upcoming(client, days=21, now=NOW)

        assert len(result) == 253
        assert [r.url.params["$skip"] for r in seen] == ["0", "250"]

    async def test_stops_paging_at_a_bound(self):
        """An API that always returns a full page must not loop forever."""
        client, seen = _client(
            lambda r: httpx.Response(200, json={"value": [_row() for _ in range(250)]})
        )

        await list_upcoming(client, days=21, now=NOW)

        assert len(seen) == 4

    async def test_error_raises(self):
        client, _ = _client(lambda r: httpx.Response(503, json={"value": []}))
        with pytest.raises(TkApiError):
            await list_upcoming(client, days=21, now=NOW)

    async def test_unexpected_shape_raises(self):
        client, _ = _client(lambda r: httpx.Response(200, json={"value": "x"}))
        with pytest.raises(TkApiError):
            await list_upcoming(client, days=21, now=NOW)


def _stub_mattermost(
    monkeypatch,
    *,
    enabled=True,
    permissions=None,
    names=None,
    slugs=None,
    base_url="https://mm.example",
):
    """Replace what the routes ask of Mattermost."""
    if permissions is None:
        permissions = {TEAM: {"create_public_channel"}}

    async def is_enabled(self):
        return enabled

    async def team_permissions(self):
        if isinstance(permissions, Exception):
            raise permissions
        return permissions

    async def team_namen(self):
        return names if names is not None else {TEAM: "NLDD"}

    async def team_slugs(self):
        return slugs if slugs is not None else {TEAM: "nldd"}

    async def get_base_url(self):
        return base_url

    for name, fn in {
        "is_enabled": is_enabled,
        "team_permissions": team_permissions,
        "team_namen": team_namen,
        "team_slugs": team_slugs,
        "base_url": get_base_url,
    }.items():
        monkeypatch.setattr(MattermostService, name, fn)


def _stub_upcoming(monkeypatch, result):
    async def fake(client, *, days, now=None, base_url=None):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(routes, "list_upcoming", fake)


@pytest.mark.asyncio
class TestAankomendEndpoint:
    async def test_lists_debates_and_teams(self, client, monkeypatch):
        activiteit = _activiteit(nummer="2099A05428")
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        resp = await client.get("/api/debatten/aankomend")

        assert resp.status_code == 200
        body = resp.json()
        assert body["teams"] == [
            {"team_id": TEAM, "team_name": "NLDD", "can_create_channel": True}
        ]
        assert body["mattermost_melding"] is None
        (debat,) = body["debatten"]
        assert debat["activiteit_id"] == activiteit.id
        assert debat["onderwerp"] == "Digitaliserende overheid"
        assert debat["soort"] == "Commissiedebat"
        assert debat["agenda_url"].endswith("details?id=2099A05428")
        assert debat["kanalen"] == []

    async def test_shows_the_channel_a_debate_already_has(
        self, client, db_session, monkeypatch
    ):
        activiteit = _activiteit()
        db_session.add(
            DebatSessie(
                activiteit_id=activiteit.id,
                onderwerp="x",
                team_id=TEAM,
                channel_id=f"chan{uuid.uuid4().hex}"[:26],
                channel_name="debat-digitaliserende-overheid-6-okt",
            )
        )
        await db_session.flush()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        resp = await client.get("/api/debatten/aankomend")

        assert resp.json()["debatten"][0]["kanalen"] == [
            {
                "team_id": TEAM,
                "channel_name": "debat-digitaliserende-overheid-6-okt",
                "channel_url": (
                    "https://mm.example/nldd/channels/"
                    "debat-digitaliserende-overheid-6-okt"
                ),
            }
        ]

    async def test_a_claim_without_channel_is_not_shown_as_a_channel(
        self, client, db_session, monkeypatch
    ):
        activiteit = _activiteit()
        db_session.add(
            DebatSessie(activiteit_id=activiteit.id, onderwerp="x", team_id=TEAM)
        )
        await db_session.flush()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        resp = await client.get("/api/debatten/aankomend")

        assert resp.json()["debatten"][0]["kanalen"] == []

    async def test_without_team_slug_there_is_a_name_but_no_link(
        self, client, db_session, monkeypatch
    ):
        activiteit = _activiteit()
        db_session.add(
            DebatSessie(
                activiteit_id=activiteit.id,
                onderwerp="x",
                team_id=TEAM,
                channel_id=f"chan{uuid.uuid4().hex}"[:26],
                channel_name="debat-x",
            )
        )
        await db_session.flush()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch, slugs={})

        resp = await client.get("/api/debatten/aankomend")

        (kanaal,) = resp.json()["debatten"][0]["kanalen"]
        assert kanaal["channel_name"] == "debat-x"
        assert kanaal["channel_url"] is None

    async def test_team_without_the_permission_is_listed_as_such(
        self, client, monkeypatch
    ):
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, permissions={TEAM: {"list_team_channels"}})

        resp = await client.get("/api/debatten/aankomend")

        assert resp.json()["teams"][0]["can_create_channel"] is False

    @pytest.mark.parametrize(
        ("kwargs", "melding"),
        [
            ({"enabled": False}, "Mattermost staat niet aan."),
            (
                {"permissions": MattermostUnavailableError("down")},
                "Mattermost is nu niet bereikbaar.",
            ),
            ({"permissions": {}}, "De bot is van geen enkel Mattermost-team lid."),
        ],
    )
    async def test_agenda_is_shown_also_when_mattermost_is_not_there(
        self, client, monkeypatch, kwargs, melding
    ):
        """The list is worth having without Mattermost; only starting is off."""
        _stub_upcoming(monkeypatch, [_activiteit()])
        _stub_mattermost(monkeypatch, **kwargs)

        resp = await client.get("/api/debatten/aankomend")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["debatten"]) == 1
        assert body["teams"] == []
        assert body["mattermost_melding"] == melding

    async def test_tk_api_down_is_503(self, client, monkeypatch):
        _stub_upcoming(monkeypatch, TkApiError("down"))
        _stub_mattermost(monkeypatch)

        resp = await client.get("/api/debatten/aankomend")

        assert resp.status_code == 503

    @pytest.mark.parametrize("dagen", [0, 61, -1])
    async def test_window_is_bounded(self, client, monkeypatch, dagen):
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)
        resp = await client.get(f"/api/debatten/aankomend?dagen={dagen}")
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestStartInTeam:
    """The service from the web app: no convocatie, no thread."""

    async def test_creates_without_an_item_or_a_user(self, db_session, monkeypatch):
        activiteit = _activiteit()
        _patch_fetch(monkeypatch, activiteit)
        mm = FakeMattermost()

        result = await DebatKanaalService(db_session, mm).start_in_team(
            activiteit_id=activiteit.id, team_id=TEAM
        )

        assert result.outcome is StartOutcome.CREATED
        assert result.channel_name == "debat-digitaliserende-overheid-6-okt"
        assert mm.created[0]["team_id"] == TEAM
        # Nobody to add, nobody to mention, and no thread to answer in.
        assert mm.members == []
        assert mm.replies == []
        assert [root for _, _, root in mm.messages] == [None]
        (sessie,) = await _sessies(db_session, activiteit.id)
        assert sessie.parlementair_item_id is None
        assert sessie.started_by_mattermost_user_id is None

    async def test_adds_the_user_when_there_is_one(self, db_session, monkeypatch):
        activiteit = _activiteit()
        _patch_fetch(monkeypatch, activiteit)
        mm = FakeMattermost()

        result = await DebatKanaalService(db_session, mm).start_in_team(
            activiteit_id=activiteit.id, team_id=TEAM, mattermost_user_id="user1"
        )

        assert mm.members == [(result.channel_id, "user1")]

    async def test_existing_channel_comes_back_with_its_name(
        self, db_session, monkeypatch
    ):
        activiteit = _activiteit()
        _patch_fetch(monkeypatch, activiteit)
        mm = FakeMattermost()
        svc = DebatKanaalService(db_session, mm)
        first = await svc.start_in_team(activiteit_id=activiteit.id, team_id=TEAM)

        second = await svc.start_in_team(activiteit_id=activiteit.id, team_id=TEAM)

        assert second.outcome is StartOutcome.EXISTS
        assert second.channel_name == first.channel_name
        assert mm.members == []

    async def test_retry_hint_is_about_the_web_app(self, db_session, monkeypatch):
        """ "Remove your reaction" means nothing to someone in the browser."""
        _patch_fetch(monkeypatch, TkApiError("down"))
        mm = FakeMattermost()

        result = await DebatKanaalService(db_session, mm).start_in_team(
            activiteit_id=str(uuid.uuid4()), team_id=TEAM
        )

        assert result.outcome is StartOutcome.FAILED
        assert RETRY_HINT_WEB in result.message
        assert "reactie" not in result.message

    async def test_unexpected_error_is_a_result_not_an_exception(
        self, db_session, monkeypatch
    ):
        async def exploding(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(service_mod, "fetch_activiteit", exploding)

        result = await DebatKanaalService(db_session, FakeMattermost()).start_in_team(
            activiteit_id=str(uuid.uuid4()), team_id=TEAM
        )

        assert result.outcome is StartOutcome.FAILED
        assert RETRY_HINT_WEB in result.message


def _stub_service(
    monkeypatch, fake_mm: FakeMattermost, activiteit: Activiteit | Exception
):
    """Let the route build the real service on a fake Mattermost."""
    _patch_fetch(monkeypatch, activiteit)
    real_init = DebatKanaalService.__init__

    def init(self, session, mattermost=None):
        real_init(self, session, fake_mm)

    monkeypatch.setattr(DebatKanaalService, "__init__", init)


@pytest.mark.asyncio
class TestStartEndpoint:
    async def test_creates_and_returns_the_channel_with_a_link(
        self, client, db_session, monkeypatch
    ):
        activiteit = _activiteit()
        mm = FakeMattermost()
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)

        resp = await client.post(
            "/api/debatten/start",
            json={"activiteit_id": activiteit.id, "team_id": TEAM},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "outcome": "created",
            "melding": None,
            "kanaal": {
                "team_id": TEAM,
                "channel_name": "debat-digitaliserende-overheid-6-okt",
                "channel_url": (
                    "https://mm.example/nldd/channels/"
                    "debat-digitaliserende-overheid-6-okt"
                ),
            },
        }
        assert mm.created[0]["team_id"] == TEAM
        assert len(await _sessies(db_session, activiteit.id)) == 1

    async def test_refusal_is_200_with_the_reason(self, client, monkeypatch):
        activiteit = _activiteit(status="Geannuleerd")
        mm = FakeMattermost()
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)

        resp = await client.post(
            "/api/debatten/start",
            json={"activiteit_id": activiteit.id, "team_id": TEAM},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "outcome": "refused",
            "melding": "Deze vergadering is geannuleerd.",
            "kanaal": None,
        }
        assert mm.created == []

    async def test_team_the_bot_is_not_in_is_refused(self, client, monkeypatch):
        """The team id comes from the browser. The bot only creates
        channels where it is a member."""
        activiteit = _activiteit()
        mm = FakeMattermost()
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)

        resp = await client.post(
            "/api/debatten/start",
            json={
                "activiteit_id": activiteit.id,
                "team_id": "team00000000000000000000zz",
            },
        )

        assert resp.status_code == 400
        assert mm.created == []

    async def test_mattermost_off_is_503(self, client, monkeypatch):
        _stub_mattermost(monkeypatch, enabled=False)
        resp = await client.post(
            "/api/debatten/start",
            json={"activiteit_id": str(uuid.uuid4()), "team_id": TEAM},
        )
        assert resp.status_code == 503

    async def test_unreachable_mattermost_is_503(self, client, monkeypatch):
        _stub_mattermost(monkeypatch, permissions=MattermostUnavailableError("down"))
        resp = await client.post(
            "/api/debatten/start",
            json={"activiteit_id": str(uuid.uuid4()), "team_id": TEAM},
        )
        assert resp.status_code == 503

    async def test_activiteit_id_must_be_a_uuid(self, client, monkeypatch):
        _stub_mattermost(monkeypatch)
        resp = await client.post(
            "/api/debatten/start",
            json={"activiteit_id": "2026A05428", "team_id": TEAM},
        )
        assert resp.status_code == 422
