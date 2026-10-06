"""Tests for the debates that were followed and are over, and for refusing
to set up a channel for a debate that has ended.

Debat Direct, the TK API and Mattermost are stubbed at their service
boundary; the sessies, the turns and the markeringen are in a real database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from bouwmeester.models.debat_markering import (
    SOORT_TOEZEGGING,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    DebatMarkering,
)
from bouwmeester.models.debat_sessie import (
    TIJDLIJN_AFGELAST,
    TIJDLIJN_AFGELOPEN,
    TIJDLIJN_GEKOPPELD,
    TIJDLIJN_LOOPT,
    DebatSessie,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_direct as dd
from bouwmeester.services import debat_stand
from bouwmeester.services.tk_activiteit import LOOKBACK, TkApiError
from tests.test_debat_kanaal import TEAM, FakeMattermost, _activiteit, _sessies
from tests.test_debatten_api import (
    OTHER_TEAM,
    TWO_TEAMS,
    _stub_agenda,
    _stub_mattermost,
    _stub_service,
    _stub_upcoming,
)
from tests.test_debatten_nu_en_stop import _part

URL = "/api/debatten/gevolgd"


@pytest.fixture(autouse=True)
def _no_debat_direct(monkeypatch):
    _stub_agenda(monkeypatch, dd.DebatDirectError("niet in een test"))
    yield
    debat_stand.AGENDA.clear()


@pytest.fixture
async def people(db_session):
    """A reader in one of two teams, and people who get nothing."""
    from bouwmeester.models.mattermost_user import MattermostUser
    from tests.factories import grant_role, make_org, make_person

    org = await make_org(db_session, f"Directie {uuid.uuid4().hex[:6]}")
    # `viewer` carries parlementair:read.
    reader = await make_person(db_session, "Meelezer")
    await grant_role(db_session, reader, "viewer", org)
    unlinked = await make_person(db_session, "Zonder koppeling")
    await grant_role(db_session, unlinked, "viewer", org)
    outsider = await make_person(db_session, "Zonder rol")
    db_session.add(
        MattermostUser(
            person_id=reader.id,
            # The account `TWO_TEAMS` puts in TEAM and not in OTHER_TEAM.
            mattermost_user_id="mmreviewer0000000000000000",
            mattermost_username="meelezer",
        )
    )
    await db_session.flush()
    return SimpleNamespace(reader=reader, unlinked=unlinked, outsider=outsider)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _sessie(**overrides) -> DebatSessie:
    """A sessie with a channel whose debate ended days ago."""
    values = {
        "id": uuid.uuid4(),
        "activiteit_id": str(uuid.uuid4()),
        "activiteit_nummer": "2099A05428",
        "onderwerp": "Digitaliserende overheid",
        "aanvang": _now() - timedelta(days=3),
        "team_id": TEAM,
        "channel_id": f"chan{uuid.uuid4().hex}"[:26],
        "channel_name": "debat-digitaliserende-overheid-6-okt",
        "tijdlijn_status": TIJDLIJN_AFGELOPEN,
    }
    values.update(overrides)
    return DebatSessie(**values)


def _of(activiteit, **overrides) -> DebatSessie:
    """The sessie of this activiteit, not closed by the timeline."""
    values = {
        "activiteit_id": activiteit.id,
        "aanvang": activiteit.aanvang,
        "tijdlijn_status": None,
    }
    values.update(overrides)
    return _sessie(**values)


def _beurt(sessie: DebatSessie, n: int, *, post: bool = True) -> DebatSpreekbeurt:
    return DebatSpreekbeurt(
        sessie_id=sessie.id,
        debat_direct_id="dd-1",
        event_type=dd.EVENT_SPEAKER,
        event_start=_now() - timedelta(days=3) + timedelta(minutes=n),
        object_id=f"spreker-{n}",
        post_id=f"post{uuid.uuid4().hex}"[:26] if post else None,
    )


def _markering(sessie: DebatSessie, n: int, **overrides) -> DebatMarkering:
    values = {
        "sessie_id": sessie.id,
        "beurt_sleutel": f"beurt-{n}",
        "volgnummer": n,
        "status": STATUS_OPEN,
        "channel_id": sessie.channel_id,
        "spreker": "Kamerlid A",
        "gericht_aan": "de staatssecretaris",
        "citaat": "Wanneer komt de brief?",
        "samenvatting": "Vraagt naar de brief.",
        "moment": _now() - timedelta(days=3),
    }
    values.update(overrides)
    return DebatMarkering(**values)


async def _add(db_session, *rows) -> None:
    db_session.add_all(rows)
    await db_session.flush()


async def _gevolgd(client, **params) -> dict:
    resp = await client.get(URL, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _ids(client, **params) -> list[str]:
    return [d["sessie_id"] for d in (await _gevolgd(client, **params))["debatten"]]


async def _aankomend_ids(client) -> list[str]:
    resp = await client.get("/api/debatten/aankomend")
    assert resp.status_code == 200, resp.text
    return [d["activiteit_id"] for d in resp.json()["debatten"]]


@pytest.mark.asyncio
class TestGevolgd:
    async def test_a_debate_that_is_over_is_listed_with_its_channel(
        self, client, db_session, monkeypatch
    ):
        sessie = _sessie()
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        body = await _gevolgd(client)

        assert body["totaal"] == 1
        assert body["limit"] == 20
        assert body["offset"] == 0
        (debat,) = body["debatten"]
        assert debat == {
            "sessie_id": str(sessie.id),
            "activiteit_id": sessie.activiteit_id,
            "nummer": "2099A05428",
            "onderwerp": "Digitaliserende overheid",
            "aanvang": sessie.aanvang.isoformat().replace("+00:00", "Z"),
            "agenda_url": debat["agenda_url"],
            "kanaal": {
                "team_id": TEAM,
                "channel_name": "debat-digitaliserende-overheid-6-okt",
                "channel_url": (
                    "https://mm.example/nldd/channels/"
                    "debat-digitaliserende-overheid-6-okt"
                ),
                "sessie_id": str(sessie.id),
                "tijdlijn_status": "afgelopen",
                "wordt_gevolgd": False,
            },
            "afloop": "afgelopen",
            "berichten": 0,
            "vragen": 0,
            "vragen_open": 0,
        }
        assert debat["agenda_url"].endswith("details?id=2099A05428")

    async def test_without_a_nummer_there_is_no_link_to_the_agenda(
        self, client, db_session, monkeypatch
    ):
        await _add(db_session, _sessie(activiteit_nummer=None))
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        (debat,) = (await _gevolgd(client))["debatten"]

        assert debat["agenda_url"] is None

    async def test_how_it_ended_is_what_the_timeline_stored(
        self, client, db_session, monkeypatch
    ):
        old = _now() - timedelta(days=2)
        afgelast = _sessie(tijdlijn_status=TIJDLIJN_AFGELAST, aanvang=old)
        never_closed = _sessie(
            tijdlijn_status=TIJDLIJN_GEKOPPELD, aanvang=old - timedelta(days=1)
        )
        await _add(db_session, afgelast, never_closed)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        debatten = (await _gevolgd(client))["debatten"]

        assert [d["afloop"] for d in debatten] == ["afgelast", None]

    async def test_newest_first_and_without_a_start_last(
        self, client, db_session, monkeypatch
    ):
        now = _now()
        oldest = _sessie(aanvang=now - timedelta(days=9))
        newest = _sessie(aanvang=now - timedelta(days=1))
        middle = _sessie(aanvang=now - timedelta(days=4))
        undated = _sessie(aanvang=None)
        await _add(db_session, oldest, newest, middle, undated)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        assert await _ids(client) == [
            str(s.id) for s in (newest, middle, oldest, undated)
        ]

    async def test_a_claim_without_a_channel_is_not_a_followed_debate(
        self, client, db_session, monkeypatch
    ):
        await _add(
            db_session,
            _sessie(channel_id=None, channel_name=None),
            _sessie(channel_name=None),
        )
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        assert await _gevolgd(client) == {
            "debatten": [],
            "totaal": 0,
            "limit": 20,
            "offset": 0,
        }

    async def test_a_debate_that_is_still_to_come_is_not_listed(
        self, client, db_session, monkeypatch
    ):
        activiteit = _activiteit()
        await _add(db_session, _of(activiteit))
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        assert await _ids(client) == []

    async def test_a_debate_far_ahead_that_was_stopped_is_listed(
        self, client, db_session, monkeypatch
    ):
        """Beyond the weeks the upcoming list shows, and stopped by hand: on
        neither list otherwise."""
        sessie = _sessie(aanvang=_now() + timedelta(days=40))
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        assert await _ids(client) == [str(sessie.id)]

    async def test_mattermost_is_not_asked_whether_the_channel_still_exists(
        self, client, db_session, monkeypatch
    ):
        sessie = _sessie()
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, gone={sessie.channel_id})

        assert await _ids(client) == [str(sessie.id)]

    async def test_without_a_browser_address_there_is_a_name_and_no_link(
        self, client, db_session, monkeypatch
    ):
        await _add(db_session, _sessie())
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, base_url="http://mattermost:8065")

        (debat,) = (await _gevolgd(client))["debatten"]

        assert debat["kanaal"]["channel_url"] is None
        assert debat["kanaal"]["channel_name"]


@pytest.mark.asyncio
class TestOneOfTheTwoLists:
    """A debate with a channel is on the upcoming list or on this one."""

    async def _both(self, client) -> tuple[list[str], list[str]]:
        return await _aankomend_ids(client), await _ids(client)

    async def test_stopped_while_the_meeting_is_still_planned_stays_upcoming(
        self, client, db_session, monkeypatch
    ):
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=1), einde=now + timedelta(hours=2)
        )
        await _add(db_session, _of(activiteit, tijdlijn_status=TIJDLIJN_AFGELOPEN))
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        assert await self._both(client) == ([activiteit.id], [])

    async def test_past_its_planned_end_moves_to_followed(
        self, client, db_session, monkeypatch
    ):
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=3), einde=now - timedelta(minutes=30)
        )
        sessie = _of(activiteit, tijdlijn_status=TIJDLIJN_AFGELOPEN)
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        assert await self._both(client) == ([], [str(sessie.id)])

    @pytest.mark.parametrize("tijdlijn", [None, TIJDLIJN_GEKOPPELD, TIJDLIJN_LOOPT])
    async def test_dropped_from_upcoming_before_the_timeline_closed_it(
        self, client, db_session, monkeypatch, tijdlijn
    ):
        """Hours inside the reach of the upcoming list, which no longer
        shows it: without this it would be on neither."""
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=3), einde=now - timedelta(minutes=30)
        )
        sessie = _of(activiteit, tijdlijn_status=tijdlijn)
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)

        assert await self._both(client) == ([], [str(sessie.id)])

    @pytest.mark.parametrize("tijdlijn", [TIJDLIJN_LOOPT, TIJDLIJN_AFGELOPEN])
    async def test_past_its_planned_end_but_running_stays_upcoming(
        self, client, db_session, monkeypatch, tijdlijn
    ):
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=3), einde=now - timedelta(minutes=30)
        )
        await _add(db_session, _of(activiteit, tijdlijn_status=tijdlijn))
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_agenda(
            monkeypatch,
            [_part(starts_at=activiteit.aanvang, started_at=activiteit.aanvang)],
        )

        assert await self._both(client) == ([activiteit.id], [])

    async def test_running_late_is_recognised_by_the_parts_the_timeline_found(
        self, client, db_session, monkeypatch
    ):
        """Begun two hours late it no longer matches its planned start; the
        sessie knows which debate it is, here as on the upcoming list."""
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=5), einde=now - timedelta(minutes=30)
        )
        await _add(
            db_session,
            _of(activiteit, tijdlijn_status=TIJDLIJN_LOOPT, debat_direct_ids=["late"]),
        )
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_agenda(
            monkeypatch,
            [
                _part(
                    starts_at=now - timedelta(hours=3),
                    started_at=now - timedelta(hours=3),
                    debate_id="late",
                )
            ],
        )

        assert await self._both(client) == ([activiteit.id], [])

    async def test_cancelled_is_gone_from_the_agenda_and_listed_here(
        self, client, db_session, monkeypatch
    ):
        sessie = _sessie(
            tijdlijn_status=TIJDLIJN_AFGELAST, aanvang=_now() + timedelta(days=2)
        )
        await _add(db_session, sessie)
        # The agenda leaves out what was cancelled or moved.
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        assert await self._both(client) == ([], [str(sessie.id)])

    async def test_a_channel_of_another_team_does_not_keep_it_off_this_list(
        self, db_session, people, monkeypatch
    ):
        """Whether the meeting counts as running is decided with the parts
        of the teams of this person alone, as on the upcoming list."""
        from tests.factories import client_as

        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=5), einde=now - timedelta(minutes=30)
        )
        mine = _of(activiteit, tijdlijn_status=TIJDLIJN_AFGELOPEN)
        theirs = _of(
            activiteit,
            team_id=OTHER_TEAM,
            tijdlijn_status=TIJDLIJN_LOOPT,
            debat_direct_ids=["late"],
        )
        await _add(db_session, mine, theirs)
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch, **TWO_TEAMS)
        _stub_agenda(
            monkeypatch,
            [
                _part(
                    starts_at=now - timedelta(hours=3),
                    started_at=now - timedelta(hours=3),
                    debate_id="late",
                )
            ],
        )

        async with client_as(db_session, people.reader) as c:
            assert await self._both(c) == ([], [str(mine.id)])


@pytest.mark.asyncio
class TestWithoutTheAgenda:
    """The Kamer cannot be read: the upcoming list shows nothing, and this
    one goes by the timeline and by how far back that list reaches."""

    async def test_what_the_timeline_closed_is_listed(
        self, client, db_session, monkeypatch
    ):
        sessie = _sessie(aanvang=_now() - timedelta(hours=2))
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, TkApiError("down"))
        _stub_mattermost(monkeypatch)

        assert await _ids(client) == [str(sessie.id)]

    async def test_within_the_reach_of_the_upcoming_list_is_not_called_over(
        self, client, db_session, monkeypatch
    ):
        await _add(
            db_session,
            _sessie(
                aanvang=_now() - LOOKBACK + timedelta(minutes=5),
                tijdlijn_status=TIJDLIJN_LOOPT,
            ),
        )
        _stub_upcoming(monkeypatch, TkApiError("down"))
        _stub_mattermost(monkeypatch)

        assert await _ids(client) == []

    async def test_beyond_the_reach_of_the_upcoming_list_is_over(
        self, client, db_session, monkeypatch
    ):
        sessie = _sessie(
            aanvang=_now() - LOOKBACK - timedelta(minutes=5),
            tijdlijn_status=TIJDLIJN_LOOPT,
        )
        await _add(db_session, sessie)
        _stub_upcoming(monkeypatch, TkApiError("down"))
        _stub_mattermost(monkeypatch)

        assert await _ids(client) == [str(sessie.id)]


@pytest.mark.asyncio
class TestCounts:
    async def test_messages_and_questions_per_debate(
        self, client, db_session, monkeypatch
    ):
        now = _now()
        busy = _sessie(aanvang=now - timedelta(days=1))
        quiet = _sessie(aanvang=now - timedelta(days=2))
        await _add(db_session, busy, quiet)
        await _add(
            db_session,
            _beurt(busy, 1),
            _beurt(busy, 2),
            # Dealt with and deliberately not posted: not a message.
            _beurt(busy, 3, post=False),
            _beurt(quiet, 1, post=False),
            _markering(busy, 1),
            _markering(busy, 2, status=STATUS_BEANTWOORD),
            _markering(busy, 3),
            # Not a question.
            _markering(busy, 4, soort=SOORT_TOEZEGGING),
        )
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        debatten = (await _gevolgd(client))["debatten"]

        assert [(d["berichten"], d["vragen"], d["vragen_open"]) for d in debatten] == [
            (2, 3, 2),
            (0, 0, 0),
        ]

    async def test_the_counts_are_two_queries_whatever_the_number_of_rows(
        self, client, db_session, monkeypatch
    ):
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)
        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        async def count_for(n: int) -> int:
            sessies = [_sessie() for _ in range(n)]
            await _add(db_session, *sessies)
            await _add(
                db_session,
                *[_beurt(s, 1) for s in sessies],
                *[_markering(s, 1) for s in sessies],
            )
            statements.clear()
            body = await _gevolgd(client)
            assert all(d["berichten"] == 1 for d in body["debatten"])
            assert all(d["vragen_open"] == 1 for d in body["debatten"])
            return len(statements)

        sync_conn = db_session.bind.sync_connection
        event.listen(sync_conn, "before_cursor_execute", record)
        try:
            one = await count_for(1)
            six = await count_for(5)
        finally:
            event.remove(sync_conn, "before_cursor_execute", record)

        assert one == six
        counting = [s for s in statements if "GROUP BY" in s]
        assert len(counting) == 2


@pytest.mark.asyncio
class TestPaging:
    async def _seven(self, db_session) -> list[str]:
        now = _now()
        sessies = [_sessie(aanvang=now - timedelta(days=n + 1)) for n in range(7)]
        await _add(db_session, *sessies)
        return [str(s.id) for s in sessies]

    async def test_a_page_and_the_total_of_everything(
        self, client, db_session, monkeypatch
    ):
        ids = await self._seven(db_session)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        first = await _gevolgd(client, limit=3)
        second = await _gevolgd(client, limit=3, offset=3)
        last = await _gevolgd(client, limit=3, offset=6)

        assert [d["sessie_id"] for d in first["debatten"]] == ids[:3]
        assert [d["sessie_id"] for d in second["debatten"]] == ids[3:6]
        assert [d["sessie_id"] for d in last["debatten"]] == ids[6:]
        assert [p["totaal"] for p in (first, second, last)] == [7, 7, 7]
        assert (second["limit"], second["offset"]) == (3, 3)

    async def test_past_the_end_is_empty_with_the_total(
        self, client, db_session, monkeypatch
    ):
        await self._seven(db_session)
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        body = await _gevolgd(client, offset=50)

        assert body["debatten"] == []
        assert body["totaal"] == 7

    @pytest.mark.parametrize(
        "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "veel"}]
    )
    async def test_refuses_a_page_that_makes_no_sense(
        self, client, monkeypatch, params
    ):
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        assert (await client.get(URL, params=params)).status_code == 422

    async def test_a_hundred_is_allowed(self, client, monkeypatch):
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        assert (await _gevolgd(client, limit=100))["limit"] == 100


@pytest.mark.asyncio
class TestWhoSeesWhat:
    async def test_a_debate_of_a_team_the_person_is_not_in_is_not_listed(
        self, db_session, people, monkeypatch
    ):
        from tests.factories import client_as

        mine = _sessie(channel_name="debat-mijn")
        theirs = _sessie(team_id=OTHER_TEAM, channel_name="debat-ander")
        await _add(db_session, mine, theirs)
        await _add(
            db_session,
            _beurt(mine, 1),
            *[_beurt(theirs, n) for n in range(1, 6)],
            _markering(mine, 1),
            *[_markering(theirs, n) for n in range(1, 4)],
        )
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, **TWO_TEAMS)

        async with client_as(db_session, people.reader) as c:
            resp = await c.get(URL)

        assert resp.status_code == 200
        body = resp.json()
        assert [d["sessie_id"] for d in body["debatten"]] == [str(mine.id)]
        # Not in the total, and its turns and questions in no count.
        assert body["totaal"] == 1
        (debat,) = body["debatten"]
        assert (debat["berichten"], debat["vragen"], debat["vragen_open"]) == (1, 1, 1)
        assert "debat-ander" not in resp.text
        assert str(theirs.id) not in resp.text
        assert theirs.channel_id not in resp.text

    async def test_paging_past_the_own_team_does_not_reach_another(
        self, db_session, people, monkeypatch
    ):
        from tests.factories import client_as

        await _add(db_session, _sessie(), _sessie(team_id=OTHER_TEAM))
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, **TWO_TEAMS)

        async with client_as(db_session, people.reader) as c:
            resp = await c.get(URL, params={"offset": 1})

        assert resp.json()["debatten"] == []
        assert resp.json()["totaal"] == 1

    async def test_who_is_in_none_of_the_teams_gets_no_history(
        self, db_session, people, monkeypatch
    ):
        """The page offers every team to someone Mattermost says is in none,
        so that starting a channel is not blocked by a wrong answer. That
        net is not a reason to show what every team followed."""
        from tests.factories import client_as

        await _add(db_session, _sessie(), _sessie(team_id=OTHER_TEAM))
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, **{**TWO_TEAMS, "members": {}})

        async with client_as(db_session, people.reader) as c:
            resp = await c.get(URL)
            teams = (await c.get("/api/debatten/aankomend")).json()["teams"]

        assert resp.json() == {"debatten": [], "totaal": 0, "limit": 20, "offset": 0}
        # The net itself is still there for starting.
        assert len(teams) == 2

    async def test_without_a_linked_account_there_is_nothing(
        self, db_session, people, monkeypatch
    ):
        from tests.factories import client_as

        await _add(db_session, _sessie())
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, **TWO_TEAMS)

        async with client_as(db_session, people.unlinked) as c:
            resp = await c.get(URL)

        assert resp.status_code == 200
        assert resp.json()["debatten"] == []
        assert resp.json()["totaal"] == 0

    async def test_without_the_permission_it_is_refused(
        self, db_session, people, monkeypatch
    ):
        from tests.factories import client_as

        await _add(db_session, _sessie())
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch)

        async with client_as(db_session, people.outsider) as c:
            resp = await c.get(URL)

        assert resp.status_code == 403
        assert "debat-" not in resp.text

    @pytest.mark.parametrize(
        "mattermost", [{"enabled": False}, {"permissions": ValueError("stuk")}]
    )
    async def test_without_mattermost_there_is_nothing(
        self, db_session, people, monkeypatch, mattermost
    ):
        """Which teams a person is in cannot be asked, so nothing is shown
        rather than everything."""
        from tests.factories import client_as

        await _add(db_session, _sessie())
        _stub_upcoming(monkeypatch, [])
        _stub_mattermost(monkeypatch, **mattermost)

        async with client_as(db_session, people.reader) as c:
            resp = await c.get(URL)

        assert resp.status_code == 200
        assert resp.json()["debatten"] == []
        assert resp.json()["totaal"] == 0


@pytest.mark.asyncio
class TestStartOfAnEndedDebate:
    """Debat Direct says it has ended: a channel set up now stays empty."""

    def _ended(self):
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=2), einde=now + timedelta(hours=1)
        )
        part = _part(
            starts_at=activiteit.aanvang,
            started_at=activiteit.aanvang,
            ended_at=now - timedelta(minutes=10),
        )
        return activiteit, part

    async def _start(self, client, activiteit, team_id=TEAM):
        return await client.post(
            "/api/debatten/start",
            json={"activiteit_id": activiteit.id, "team_id": team_id},
        )

    async def test_is_refused_and_no_channel_is_made(
        self, client, db_session, monkeypatch
    ):
        activiteit, part = self._ended()
        mm = FakeMattermost()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)
        _stub_agenda(monkeypatch, [part])
        # The page was read, so the meeting is at hand.
        assert await _aankomend_ids(client) == [activiteit.id]

        resp = await self._start(client, activiteit)

        assert resp.status_code == 200
        assert resp.json() == {
            "outcome": "refused",
            "melding": "Dit debat is afgelopen; er valt niets meer te volgen.",
            "kanaal": None,
        }
        assert mm.created == []
        assert await _sessies(db_session, activiteit.id) == []

    async def test_a_running_debate_is_started(self, client, monkeypatch):
        activiteit, part = self._ended()
        running = _part(starts_at=part.starts_at, started_at=part.started_at)
        mm = FakeMattermost()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)
        _stub_agenda(monkeypatch, [running])
        await _aankomend_ids(client)

        resp = await self._start(client, activiteit)

        assert resp.json()["outcome"] == "created"

    async def test_an_existing_channel_is_still_pointed_at(
        self, client, db_session, monkeypatch
    ):
        activiteit, part = self._ended()
        await _add(db_session, _of(activiteit, tijdlijn_status=TIJDLIJN_AFGELOPEN))
        mm = FakeMattermost()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)
        _stub_agenda(monkeypatch, [part])
        await _aankomend_ids(client)

        resp = await self._start(client, activiteit)

        assert resp.json()["outcome"] == "exists"
        assert resp.json()["kanaal"]["channel_name"]

    async def test_a_channel_in_another_team_does_not_count(
        self, client, db_session, monkeypatch
    ):
        """And what that team's timeline found says which debate it is."""
        now = _now()
        activiteit = _activiteit(
            aanvang=now - timedelta(hours=5), einde=now + timedelta(hours=1)
        )
        await _add(
            db_session,
            _of(activiteit, team_id=OTHER_TEAM, debat_direct_ids=["late"]),
        )
        mm = FakeMattermost()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)
        _stub_agenda(
            monkeypatch,
            [
                _part(
                    starts_at=now - timedelta(hours=3),
                    started_at=now - timedelta(hours=3),
                    ended_at=now - timedelta(minutes=10),
                    debate_id="late",
                )
            ],
        )
        await _aankomend_ids(client)

        resp = await self._start(client, activiteit)

        assert resp.json()["outcome"] == "refused"
        assert mm.created == []

    async def test_without_debat_direct_the_start_goes_ahead(self, client, monkeypatch):
        activiteit, _ = self._ended()
        mm = FakeMattermost()
        _stub_upcoming(monkeypatch, [activiteit])
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)
        await _aankomend_ids(client)

        resp = await self._start(client, activiteit)

        assert resp.json()["outcome"] == "created"

    async def test_a_meeting_the_page_never_read_is_not_looked_up_for_this(
        self, client, monkeypatch
    ):
        activiteit, part = self._ended()
        mm = FakeMattermost()
        _stub_mattermost(monkeypatch)
        _stub_service(monkeypatch, mm, activiteit)
        asked = _stub_agenda(monkeypatch, [part])

        resp = await self._start(client, activiteit)

        assert resp.json()["outcome"] == "created"
        # Not even Debat Direct was asked.
        assert asked == []
