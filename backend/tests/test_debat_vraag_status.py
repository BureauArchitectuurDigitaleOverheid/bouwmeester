"""Tests for what becomes of a marked question: a reaction on its reply.

The rule that turns reactions into a status is pure and tested as such. The
service that works a reaction in runs against a real database with a fake
Mattermost that keeps messages and reactions the way the real one does: a
list of reactions per post, each with who and when.

No names of people: the speakers are "Kamerlid A (X)", the readers
"persoon.a".
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import (
    SOORT_MOTIE,
    SOORT_VRAAG,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    STATUS_TOEGEWEZEN,
    STATUS_VERVALT,
    STATUS_VERWORPEN,
    DebatMarkering,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.services import debat_vraag_status_service as mod
from bouwmeester.services import debat_vraag_worker
from bouwmeester.services import mattermost_websocket_service as ws_mod
from bouwmeester.services.debat_kanaal_service import stukken_message
from bouwmeester.services.debat_statusregel import splits, statusregel
from bouwmeester.services.debat_vraag_reacties import (
    LEGENDA,
    REACTIE_BEANTWOORD,
    REACTIE_GEEN_VRAAG,
    REACTIE_HINT,
    REACTIE_OPGEPAKT,
    REACTIE_VERVALT,
    Stand,
    stand_marker,
    stand_uit_reacties,
)
from bouwmeester.services.debat_vraag_service import (
    DebatVraagService,
    format_thread,
    format_vraag_thread,
)
from bouwmeester.services.debat_vraag_status_service import (
    GEEF_OP_NA,
    MAX_PER_RONDE,
    DebatVraagStatusService,
    is_status_reactie,
    markeer_reactie,
    verworpen_markeringen,
)
from bouwmeester.services.debat_vraag_worker import DebatVraagWorker
from bouwmeester.services.mattermost_service import (
    MattermostService,
    PostNotFoundError,
)
from bouwmeester.services.tk_activiteit import Activiteit

BOT = "botbotbotbotbotbotbotbotbo"
PERSOON_A = "useraaaaaaaaaaaaaaaaaaaaaa"
PERSOON_B = "userbbbbbbbbbbbbbbbbbbbbbb"
CHANNEL = "chanstatus0000000000000000"
TEAM = "teamstatus0000000000000000"
MOMENT = datetime(2026, 10, 5, 8, 2, 23, tzinfo=UTC)
TURN = "**Kamerlid A (X)** · 10:02\nVoorzitter, ik heb een vraag."


def _reactie(user: str, emoji: str, at: int, **extra) -> dict:
    return {"user_id": user, "emoji_name": emoji, "create_at": at, **extra}


def _thread(**extra) -> str:
    values = {
        "volgnummer": 12,
        "gericht_aan": "de minister",
        "citaat": "Wanneer komt de brief naar de Kamer?",
        "samenvatting": "Wanneer de brief komt.",
        "stuk": None,
        "moment": MOMENT,
        "moment_url": None,
    }
    values.update(extra)
    return format_vraag_thread(**values)


def _stand(tekst: str) -> str:
    """What a reply says about where its question stands: icon and words.

    Read from where the layout puts them, so the tests of the service say
    "✅ beantwoord" and not how a reply is laid out.
    """
    eerste, _, rest = tekst.partition("\n")
    icoon = eerste.split(" ")[0]
    if not rest:
        # A rejected one: a single line that ends in the words.
        return f"{icoon} {eerste.rsplit('~~ · ', 1)[1]}"
    delen = rest.split("\n")[0].split(" · ")
    return f"{icoon} {delen[1]}" if len(delen) == 4 else icoon


# --- the rule ----------------------------------------------------------


class TestStandUitReacties:
    def test_no_reactions_is_open(self):
        assert stand_uit_reacties([], BOT) == Stand()
        assert Stand().status == STATUS_OPEN

    @pytest.mark.parametrize(
        ("emoji", "status"),
        [
            (REACTIE_BEANTWOORD, STATUS_BEANTWOORD),
            (REACTIE_OPGEPAKT, STATUS_TOEGEWEZEN),
            (REACTIE_VERVALT, STATUS_VERVALT),
            (REACTIE_GEEN_VRAAG, STATUS_VERWORPEN),
        ],
    )
    def test_each_reaction_is_a_status(self, emoji, status):
        stand = stand_uit_reacties([_reactie(PERSOON_A, emoji, 1_000)], BOT)
        assert stand.status == status
        assert stand.mattermost_user_id == PERSOON_A
        assert stand.sinds == datetime.fromtimestamp(1, UTC)

    def test_the_names_are_the_ones_mattermost_uses(self):
        # Checked against the emoji list of Mattermost: 🚫 is
        # `no_entry_sign`; `no_entry` is ⛔, another emoji.
        assert REACTIE_BEANTWOORD == "white_check_mark"
        assert REACTIE_OPGEPAKT == "eyes"
        assert REACTIE_VERVALT == "no_entry_sign"
        assert REACTIE_GEEN_VRAAG == "x"

    def test_the_latest_reaction_decides_whoever_put_it(self):
        stand = stand_uit_reacties(
            [
                _reactie(PERSOON_B, REACTIE_BEANTWOORD, 3_000),
                _reactie(PERSOON_A, REACTIE_OPGEPAKT, 1_000),
                _reactie(PERSOON_A, REACTIE_GEEN_VRAAG, 2_000),
            ],
            BOT,
        )
        assert (stand.status, stand.mattermost_user_id) == (
            STATUS_BEANTWOORD,
            PERSOON_B,
        )

    def test_the_bot_itself_never_sets_a_status(self):
        stand = stand_uit_reacties([_reactie(BOT, REACTIE_HINT, 9_000)], BOT)
        assert stand == Stand()

    def test_the_bot_does_not_outvote_a_person(self):
        stand = stand_uit_reacties(
            [
                _reactie(PERSOON_A, REACTIE_OPGEPAKT, 1_000),
                _reactie(BOT, REACTIE_HINT, 9_000),
            ],
            BOT,
        )
        assert stand.status == STATUS_TOEGEWEZEN

    def test_another_emoji_means_nothing(self):
        stand = stand_uit_reacties(
            [
                _reactie(PERSOON_A, REACTIE_OPGEPAKT, 1_000),
                _reactie(PERSOON_B, "thumbsup", 9_000),
                _reactie(PERSOON_B, "no_entry", 9_500),
            ],
            BOT,
        )
        assert (stand.status, stand.mattermost_user_id) == (
            STATUS_TOEGEWEZEN,
            PERSOON_A,
        )

    def test_a_reaction_that_was_taken_away_is_skipped(self):
        stand = stand_uit_reacties(
            [_reactie(PERSOON_A, REACTIE_BEANTWOORD, 1_000, delete_at=2_000)], BOT
        )
        assert stand == Stand()

    def test_at_the_same_moment_the_later_one_in_the_list_decides(self):
        stand = stand_uit_reacties(
            [
                _reactie(PERSOON_A, REACTIE_OPGEPAKT, 1_000),
                _reactie(PERSOON_B, REACTIE_BEANTWOORD, 1_000),
            ],
            BOT,
        )
        assert stand.status == STATUS_BEANTWOORD

    def test_rubbish_in_the_list_is_skipped(self):
        stand = stand_uit_reacties(
            [
                "geen reactie",
                {"emoji_name": REACTIE_BEANTWOORD},
                {"user_id": PERSOON_A, "emoji_name": None},
                _reactie(PERSOON_A, REACTIE_VERVALT, "geen getal"),
            ],
            BOT,
        )
        assert (stand.status, stand.mattermost_user_id) == (STATUS_VERVALT, PERSOON_A)
        # Without a usable moment there is no "since".
        assert stand.sinds is None

    def test_which_emoji_are_looked_at_at_all(self):
        assert is_status_reactie("x")
        assert is_status_reactie("no_entry_sign")
        assert not is_status_reactie("thumbsup")
        assert not is_status_reactie("headphones")
        assert not is_status_reactie("")


# --- what the channel shows --------------------------------------------


OPEN = (
    "❓ **Wanneer de brief komt.**\n"
    "Vraag 12 · aan de minister · 10:02 (begin van de spreekbeurt)\n"
    "> Wanneer komt de brief naar de Kamer?\n"
    "\n"
    "_Citaten komen letterlijk uit het automatische transcript._"
)


class TestDeThread:
    def test_an_open_question_looks_as_it_did(self):
        assert _thread() == OPEN
        assert _thread(status=STATUS_OPEN) == OPEN

    @pytest.mark.parametrize(
        ("status", "icoon", "woorden"),
        [
            (STATUS_BEANTWOORD, "✅", "beantwoord"),
            (STATUS_TOEGEWEZEN, "👀", "opgepakt"),
            (STATUS_VERVALT, "🚫", "hoeft geen antwoord"),
        ],
    )
    def test_the_icon_becomes_that_of_the_state_and_the_words_follow_the_number(
        self, status, icoon, woorden
    ):
        verwacht = OPEN.replace("❓", icoon).replace(
            "Vraag 12 · ", f"Vraag 12 · {woorden} · "
        )
        assert _thread(status=status) == verwacht
        # Once each, and no question mark left next to the icon.
        assert verwacht.count(icoon) == verwacht.count(woorden) == 1
        assert "❓" not in verwacht

    def test_who_picked_it_up_is_named(self):
        tweede = _thread(status=STATUS_TOEGEWEZEN, door="persoon.a").split("\n")[1]
        assert tweede.startswith("Vraag 12 · opgepakt door persoon.a · aan de minister")

    def test_who_ticked_off_an_answer_is_not(self):
        for status in (STATUS_BEANTWOORD, STATUS_VERVALT, STATUS_VERWORPEN):
            assert _thread(status=status, door="persoon.a") == _thread(status=status)

    def test_a_name_cannot_mention_anyone_or_break_out(self):
        tweede = _thread(status=STATUS_TOEGEWEZEN, door="\\@all **vet** ~~x~~").split(
            "\n"
        )[1]
        assert "@" not in tweede
        assert " · opgepakt door all \\*\\*vet\\*\\* \\~\\~x\\~\\~ · aan " in tweede

    def test_a_name_with_a_line_break_stays_on_its_line(self):
        tekst = _thread(status=STATUS_TOEGEWEZEN, door="persoon.a\n# kop")
        assert len(tekst.split("\n")) == len(OPEN.split("\n"))

    def test_a_very_long_name_is_cut(self):
        tweede = _thread(status=STATUS_TOEGEWEZEN, door="a" * 500).split("\n")[1]
        assert len(tweede.split(" · ")[1]) < 90

    def test_a_rejected_one_is_a_single_struck_line(self):
        assert _thread(status=STATUS_VERWORPEN) == (
            "❌ ~~Vraag 12 · Wanneer de brief komt.~~ · geen vraag"
        )

    def test_a_rejected_one_without_a_summary_shows_the_quote(self):
        tekst = _thread(status=STATUS_VERWORPEN, samenvatting="")
        assert tekst == (
            "❌ ~~Vraag 12 · Wanneer komt de brief naar de Kamer?~~ · geen vraag"
        )

    @pytest.mark.parametrize(
        "extra",
        [
            {"samenvatting": "half ~~ af\nen verder"},
            {"samenvatting": "", "citaat": "Is dit half ~~ af\nen gaat het verder?"},
        ],
    )
    def test_a_tilde_in_a_rejected_one_cannot_end_the_strike(self, extra):
        tekst = _thread(status=STATUS_VERWORPEN, **extra)
        assert "\n" not in tekst
        # The two tildes of the question are escaped; only ours are bare,
        # and ours open after the icon and close before the words.
        assert tekst.replace("\\~", "").count("~~") == 2
        assert tekst.startswith("❌ ~~Vraag 12 · ")
        assert tekst.endswith("~~ · geen vraag")

    def test_a_long_rejected_one_stays_one_line(self):
        tekst = _thread(status=STATUS_VERWORPEN, samenvatting="woord " * 100)
        assert "\n" not in tekst
        assert len(tekst) < 300

    def test_a_rejected_one_has_no_note_whatever_the_reply_had(self):
        assert _thread(status=STATUS_VERWORPEN, first_in_thread=True) == _thread(
            status=STATUS_VERWORPEN, first_in_thread=False
        )

    @pytest.mark.parametrize(
        "status", [STATUS_OPEN, STATUS_BEANTWOORD, STATUS_TOEGEWEZEN, STATUS_VERVALT]
    )
    def test_the_note_is_there_only_under_the_first_reply_in_every_state(self, status):
        noot = "_Citaten komen letterlijk uit het automatische transcript._"
        met = _thread(status=status, first_in_thread=True)
        zonder = _thread(status=status, first_in_thread=False)
        assert met == f"{zonder}\n\n{noot}"
        assert noot not in zonder

    def test_the_time_of_the_question_and_its_link_stay_with_a_status(self):
        extra = {
            "vraag_moment": MOMENT + timedelta(minutes=3),
            "moment_url": "https://debatdirect.example/debat?event=speaker",
        }
        open_ = _thread(**extra).split("\n")[1]
        beantwoord = _thread(status=STATUS_BEANTWOORD, **extra).split("\n")[1]
        assert "[10:05](" in open_
        assert beantwoord == open_.replace("Vraag 12 · ", "Vraag 12 · beantwoord · ")

    def test_the_same_state_twice_is_the_same_text(self):
        for status in (STATUS_BEANTWOORD, STATUS_VERWORPEN, STATUS_TOEGEWEZEN):
            assert _thread(status=status, door="persoon.a") == _thread(
                status=status, door="persoon.a"
            )

    def test_an_unknown_status_shows_no_marker(self):
        assert _thread(status="nog_niet_bedacht") == OPEN

    def test_the_marker_is_an_icon_and_words_apart(self):
        assert stand_marker(STATUS_OPEN) == ("", "")
        assert stand_marker("nog_niet_bedacht", "persoon.a") == ("", "")
        assert stand_marker(STATUS_BEANTWOORD) == ("✅", "beantwoord")
        assert stand_marker(STATUS_VERVALT) == ("🚫", "hoeft geen antwoord")
        assert stand_marker(STATUS_VERWORPEN, "persoon.a") == ("❌", "geen vraag")
        assert stand_marker(STATUS_TOEGEWEZEN) == ("👀", "opgepakt")
        assert stand_marker(STATUS_TOEGEWEZEN, "persoon.a") == (
            "👀",
            "opgepakt door persoon.a",
        )


class TestDeStatusregel:
    def test_needs_no_answer_is_still_a_question_and_not_open(self):
        assert statusregel([(SOORT_VRAAG, STATUS_VERVALT)]) == (
            "❓ 1 vraag · hoeft geen antwoord"
        )
        assert statusregel(
            [(SOORT_VRAAG, STATUS_VERVALT), (SOORT_VRAAG, STATUS_VERVALT)]
        ) == ("❓ 2 vragen · hoeft geen antwoord")

    @pytest.mark.parametrize(
        ("status", "woord"),
        [
            (STATUS_OPEN, "🔴 **open**"),
            (STATUS_TOEGEWEZEN, "opgepakt"),
            (STATUS_BEANTWOORD, "beantwoord"),
            (STATUS_VERVALT, "hoeft geen antwoord"),
        ],
    )
    def test_one_state_is_one_word_without_a_count(self, status, woord):
        assert statusregel([(SOORT_VRAAG, status)]) == f"❓ 1 vraag · {woord}"
        assert statusregel([(SOORT_VRAAG, status)] * 3) == f"❓ 3 vragen · {woord}"

    def test_only_what_is_open_stands_out(self):
        """Someone scrolling through the channel looks for what is open: a
        line without the red dot needs nobody, and no other status has a
        sign that could be as loud."""
        klaar = statusregel(
            [(SOORT_VRAAG, STATUS_TOEGEWEZEN), (SOORT_VRAAG, STATUS_BEANTWOORD)]
        )
        assert klaar == "❓ 2 vragen · 1 opgepakt · 1 beantwoord"
        deels = statusregel(
            [(SOORT_VRAAG, STATUS_OPEN), (SOORT_VRAAG, STATUS_BEANTWOORD)]
        )
        assert deels == "❓ 2 vragen · 🔴 **1 open** · 1 beantwoord"

    def test_every_state_is_counted_in_a_fixed_order(self):
        statussen = [
            STATUS_VERWORPEN,
            STATUS_VERVALT,
            STATUS_BEANTWOORD,
            STATUS_TOEGEWEZEN,
            STATUS_OPEN,
            STATUS_VERVALT,
        ]
        verwacht = (
            "❓ 5 vragen · 🔴 **1 open** · 1 opgepakt · 1 beantwoord"
            " · 🚫 2 hoeft geen antwoord"
        )
        assert statusregel([(SOORT_VRAAG, s) for s in statussen]) == verwacht
        # Whatever order the questions were asked in.
        assert statusregel([(SOORT_VRAAG, s) for s in reversed(statussen)]) == verwacht

    def test_a_rejected_one_next_to_one_state_leaves_that_state_alone(self):
        assert statusregel(
            [(SOORT_VRAAG, STATUS_VERWORPEN), (SOORT_VRAAG, STATUS_VERVALT)]
        ) == ("❓ 1 vraag · hoeft geen antwoord")

    def test_a_turn_of_rejected_questions_only_shows_nothing(self):
        assert (
            statusregel(
                [(SOORT_VRAAG, STATUS_VERWORPEN), (SOORT_VRAAG, STATUS_VERWORPEN)]
            )
            == ""
        )


class TestDeLegenda:
    def _activiteit(self) -> Activiteit:
        return Activiteit(
            id=str(uuid.uuid4()),
            nummer="2026A00001",
            soort="Commissiedebat",
            onderwerp="Voorbeelddebat",
            aanvang=MOMENT,
            einde=None,
            status="Gepland",
            commissie=None,
            bewindspersonen=(),
            agendapunten=(),
        )

    def test_names_every_reaction(self):
        for teken in ("✅", "👀", "🚫", "❌"):
            assert teken in LEGENDA
        assert "\n" not in LEGENDA

    def test_stands_in_the_pinned_message_of_a_channel_with_questions(self):
        bericht = stukken_message(self._activiteit(), vragen=True)
        assert LEGENDA in bericht
        # Above the line that says where the agenda came from.
        assert bericht.index(LEGENDA) < bericht.index("_Uit de agenda")

    def test_not_where_no_questions_are_marked(self):
        assert LEGENDA not in stukken_message(self._activiteit())


# --- asking Mattermost for the reactions -------------------------------


def _client(status_code: int, body) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v4/posts/post1/reactions"
        # `content` and not `json`: a body of `null` has to arrive as one.
        return httpx.Response(
            status_code,
            content=json.dumps(body),
            headers={"content-type": "application/json"},
        )

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://mattermost.example"
    )


class TestUpdatePost:
    async def test_changes_only_the_text_so_reactions_and_pin_stay(self, monkeypatch):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"id": "post1"})

        service = MattermostService(None)

        async def client():
            return httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="http://mattermost.example",
            )

        monkeypatch.setattr(service, "_get_client", client)

        assert await service.update_post("post1", "nieuwe tekst", {"a": 1}) is True

        # A patch: a full update without "has reactions" and "pinned" hides
        # the reactions under the post and unpins it.
        assert (seen[0].method, seen[0].url.path) == (
            "PUT",
            "/api/v4/posts/post1/patch",
        )
        assert json.loads(seen[0].content) == {
            "message": "nieuwe tekst",
            "props": {"a": 1},
        }


class TestGetPostReactions:
    async def _get(self, monkeypatch, status_code: int, body):
        service = MattermostService(None)

        async def client():
            return _client(status_code, body)

        monkeypatch.setattr(service, "_get_client", client)
        return await service.get_post_reactions("post1")

    async def test_the_list_as_it_is(self, monkeypatch):
        reactie = _reactie(PERSOON_A, REACTIE_OPGEPAKT, 1_000)
        assert await self._get(monkeypatch, 200, [reactie]) == [reactie]

    async def test_null_is_no_reactions(self, monkeypatch):
        assert await self._get(monkeypatch, 200, None) == []

    async def test_a_failure_is_not_no_reactions(self, monkeypatch):
        assert await self._get(monkeypatch, 500, {}) is None
        assert await self._get(monkeypatch, 200, {"geen": "lijst"}) is None

    async def test_a_post_that_is_gone_says_so(self, monkeypatch):
        with pytest.raises(PostNotFoundError):
            await self._get(monkeypatch, 404, {})


# --- the service -------------------------------------------------------


class FakeMattermost:
    """Messages and reactions, kept the way Mattermost keeps them."""

    def __init__(self) -> None:
        self.messages: dict[str, str] = {}
        self.props: dict[str, dict] = {}
        self.reactions: dict[str, list[dict]] = {}
        self.updates: list[tuple[str, str]] = []
        self.update_props: list[dict | None] = []
        self.reads: list[str] = []
        self.reaction_reads: list[str] = []
        self.username_reads: list[str] = []
        self.usernames: dict[str, str] = {}
        self.gone: set[str] = set()
        self.bot: str | None = BOT
        self.enabled = True
        self.fail_reactions = 0
        self.fail_reads = 0
        self.fail_updates = 0
        self.raise_updates = 0
        # Called with the post id on every read of a message.
        self.on_read = None
        self._clock = 1_000

    def post(self, prefix: str, text: str) -> str:
        post_id = f"{prefix}{uuid.uuid4().hex}"[:26]
        self.messages[post_id] = text
        return post_id

    def react(self, post_id: str, user: str, emoji: str) -> None:
        self._clock += 1_000
        self.reactions.setdefault(post_id, []).append(
            _reactie(user, emoji, self._clock)
        )

    def unreact(self, post_id: str, user: str, emoji: str) -> None:
        self.reactions[post_id] = [
            r
            for r in self.reactions.get(post_id, [])
            if (r["user_id"], r["emoji_name"]) != (user, emoji)
        ]

    async def is_enabled(self) -> bool:
        return self.enabled

    async def get_bot_user_id(self):
        return self.bot

    async def get_username(self, user_id: str) -> str:
        self.username_reads.append(user_id)
        return self.usernames.get(user_id, user_id)

    async def add_reaction(self, post_id: str, emoji: str) -> bool:
        self.react(post_id, BOT, emoji)
        return True

    async def send_channel_message(self, channel_id, text, props=None, root_id=None):
        return self.post("reply", text)

    async def get_post_reactions(self, post_id: str):
        self.reaction_reads.append(post_id)
        if post_id in self.gone:
            raise PostNotFoundError(post_id)
        if self.fail_reactions > 0:
            self.fail_reactions -= 1
            return None
        return list(self.reactions.get(post_id, []))

    async def get_post(self, post_id: str):
        self.reads.append(post_id)
        if self.on_read is not None:
            await self.on_read(post_id)
        if post_id in self.gone:
            raise PostNotFoundError(post_id)
        if self.fail_reads > 0:
            self.fail_reads -= 1
            return None
        return {
            "id": post_id,
            "message": self.messages[post_id],
            "props": self.props.get(post_id, {}),
        }

    async def update_post(self, post_id, message, props=None) -> bool:
        if self.raise_updates > 0:
            self.raise_updates -= 1
            raise RuntimeError("mattermost is weg")
        if self.fail_updates > 0:
            self.fail_updates -= 1
            return False
        self.updates.append((post_id, message))
        self.update_props.append(props)
        self.messages[post_id] = message
        return True

    async def close(self) -> None:
        pass


async def _sessie(session: AsyncSession) -> uuid.UUID:
    sessie = DebatSessie(
        activiteit_id=str(uuid.uuid4()), onderwerp="Voorbeelddebat", team_id=TEAM
    )
    session.add(sessie)
    await session.flush()
    return sessie.id


async def _markering(
    session: AsyncSession,
    mm: FakeMattermost,
    sessie_id: uuid.UUID,
    volgnummer: int = 1,
    *,
    beurt_post_id: str | None = None,
    **extra,
) -> DebatMarkering:
    """A question that is in the channel: a turn, a reply, a status line."""
    if beurt_post_id is None:
        beurt_post_id = mm.post("post", TURN)
    values = {
        "sessie_id": sessie_id,
        "beurt_sleutel": f"post:{beurt_post_id}",
        "volgnummer": volgnummer,
        "channel_id": CHANNEL,
        "beurt_post_id": beurt_post_id,
        "spreker": "Kamerlid A (X)",
        "fractie": "X",
        "gericht_aan": "de minister",
        "citaat": f"Wanneer komt brief {volgnummer} naar de Kamer?",
        "samenvatting": f"Wanneer brief {volgnummer} komt.",
        "moment": MOMENT,
        "statusregel_at": datetime.now(UTC),
        # As for the first reply under a turn; a test that is about the
        # note says so itself.
        "met_noot": True,
    }
    values.update(extra)
    markering = DebatMarkering(**values)
    if "thread_post_id" not in extra:
        markering.thread_post_id = mm.post("reply", _tekst(markering))
    session.add(markering)
    await session.flush()
    blok = await _blok(session, beurt_post_id)
    body = splits(mm.messages[beurt_post_id])[0]
    mm.messages[beurt_post_id] = f"{body}\n\n---\n{blok}" if blok else body
    await session.commit()
    return markering


def _tekst(markering: DebatMarkering, **extra) -> str:
    return format_thread(
        markering.soort or SOORT_VRAAG,
        volgnummer=markering.volgnummer,
        gericht_aan=markering.gericht_aan,
        citaat=markering.citaat,
        samenvatting=markering.samenvatting,
        stuk=markering.stuk,
        moment=markering.moment,
        moment_url=markering.moment_url,
        vraag_moment=markering.vraag_moment,
        first_in_thread=markering.met_noot,
        **extra,
    )


async def _blok(session: AsyncSession, beurt_post_id: str) -> str:
    rows = (
        await session.execute(
            select(DebatMarkering.soort, DebatMarkering.status).where(
                DebatMarkering.beurt_post_id == beurt_post_id,
                DebatMarkering.thread_post_id.is_not(None),
            )
        )
    ).all()
    return statusregel([(r[0], r[1] or STATUS_OPEN) for r in rows])


async def _lees(session: AsyncSession, markering_id: uuid.UUID) -> DebatMarkering:
    return (
        await session.execute(
            select(DebatMarkering)
            .where(DebatMarkering.id == markering_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _reageer(
    session: AsyncSession, mm: FakeMattermost, post_id: str, user: str, emoji: str
) -> None:
    """Someone clicks, and the websocket hears it."""
    mm.react(post_id, user, emoji)
    assert await markeer_reactie(session, post_id)
    await session.commit()


async def _haal_weg(
    session: AsyncSession, mm: FakeMattermost, post_id: str, user: str, emoji: str
) -> None:
    mm.unreact(post_id, user, emoji)
    assert await markeer_reactie(session, post_id)
    await session.commit()


async def _ronde(session: AsyncSession, mm: FakeMattermost, **extra):
    return await DebatVraagStatusService(session, mm).werk_bij(**extra)


class TestEenReactieWordtEenStatus:
    @pytest.mark.parametrize(
        ("emoji", "status", "begin", "blok"),
        [
            (
                REACTIE_BEANTWOORD,
                STATUS_BEANTWOORD,
                "✅ **Wanneer brief 1 komt.**\n"
                "Vraag 1 · beantwoord · aan de minister · 10:02",
                "❓ 1 vraag · beantwoord",
            ),
            (
                REACTIE_OPGEPAKT,
                STATUS_TOEGEWEZEN,
                "👀 **Wanneer brief 1 komt.**\n"
                "Vraag 1 · opgepakt door persoon.a · aan de minister · 10:02",
                "❓ 1 vraag · opgepakt",
            ),
            (
                REACTIE_VERVALT,
                STATUS_VERVALT,
                "🚫 **Wanneer brief 1 komt.**\n"
                "Vraag 1 · hoeft geen antwoord · aan de minister · 10:02",
                "❓ 1 vraag · hoeft geen antwoord",
            ),
            (
                REACTIE_GEEN_VRAAG,
                STATUS_VERWORPEN,
                "❌ ~~Vraag 1 · Wanneer brief 1 komt.~~ · geen vraag",
                "",
            ),
        ],
    )
    async def test_it_is_stored_and_shown_in_both_places(
        self, db_session, emoji, status, begin, blok
    ):
        mm = FakeMattermost()
        mm.usernames[PERSOON_A] = "persoon.a"
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        voor = datetime.now(UTC)

        await _reageer(db_session, mm, markering.thread_post_id, PERSOON_A, emoji)
        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd, ronde.mislukt) == (1, 1, 0)
        row = await _lees(db_session, markering.id)
        assert row.status == status
        assert row.status_door_mattermost_user_id == PERSOON_A
        # Since the moment of the reaction, as Mattermost has it.
        assert row.status_at == datetime.fromtimestamp(2, UTC)
        assert row.status_door_person_id is None
        assert row.reacties_gewijzigd_at is None
        assert row.statusregel_at >= voor
        assert mm.messages[row.thread_post_id].startswith(begin)
        body, status_blok = splits(mm.messages[row.beurt_post_id])
        assert body == TURN
        assert status_blok == blok

    @pytest.mark.parametrize(
        ("emoji", "status", "begin", "blok"),
        [
            (
                REACTIE_BEANTWOORD,
                STATUS_BEANTWOORD,
                "✅ **Verzoekt de regering een plan te maken**\n"
                "Motie 1 · oordeel gegeven · ingediend · 10:02",
                "📜 1 motie · oordeel gegeven",
            ),
            (
                REACTIE_OPGEPAKT,
                STATUS_TOEGEWEZEN,
                "👀 **Verzoekt de regering een plan te maken**\n"
                "Motie 1 · opgepakt door persoon.a · ingediend · 10:02",
                "📜 1 motie · opgepakt",
            ),
            (
                REACTIE_VERVALT,
                STATUS_VERVALT,
                "🚫 **Verzoekt de regering een plan te maken**\n"
                "Motie 1 · hoeft geen oordeel · ingediend · 10:02",
                "📜 1 motie · hoeft geen oordeel",
            ),
            (
                REACTIE_GEEN_VRAAG,
                STATUS_VERWORPEN,
                "❌ ~~Motie 1 · Verzoekt de regering een plan te maken~~ · geen motie",
                "",
            ),
        ],
    )
    async def test_a_reaction_on_a_motie_says_it_in_the_words_of_a_motie(
        self, db_session, emoji, status, begin, blok
    ):
        """The same reactions and statuses; nothing about an answer."""
        mm = FakeMattermost()
        mm.usernames[PERSOON_A] = "persoon.a"
        sessie_id = await _sessie(db_session)
        markering = await _markering(
            db_session,
            mm,
            sessie_id,
            soort=SOORT_MOTIE,
            gericht_aan="",
            samenvatting="",
            citaat=(
                "verzoekt de regering een plan te maken, en gaat over tot de orde"
                " van de dag"
            ),
        )
        assert mm.messages[markering.thread_post_id].startswith(
            "📜 **Verzoekt de regering een plan te maken**\nMotie 1 · ingediend · "
        )

        await _reageer(db_session, mm, markering.thread_post_id, PERSOON_A, emoji)
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert row.status == status
        tekst = mm.messages[row.thread_post_id]
        assert tekst.startswith(begin)
        assert "vraag" not in tekst.lower()
        assert splits(mm.messages[row.beurt_post_id])[1] == blok

        # Taking the reaction away brings the reply of an open motie back.
        await _haal_weg(db_session, mm, markering.thread_post_id, PERSOON_A, emoji)
        await _ronde(db_session, mm)
        assert mm.messages[row.thread_post_id].startswith(
            "📜 **Verzoekt de regering een plan te maken**\nMotie 1 · ingediend · "
        )
        assert splits(mm.messages[row.beurt_post_id])[1] == "📜 1 motie · 🔴 **open**"

    async def test_the_reply_keeps_what_it_said(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        was = mm.messages[markering.thread_post_id]
        mm.props[markering.thread_post_id] = {"van": "de bot"}

        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        await _ronde(db_session, mm)

        # The quote, the time and the note are what they were; only the
        # icon and the words of the status are new.
        assert mm.messages[markering.thread_post_id] == was.replace("❓", "✅").replace(
            "Vraag 1 · ", "Vraag 1 · beantwoord · "
        )
        assert "> Wanneer komt brief 1 naar de Kamer?" in was
        # The props go back with the edit, or the edit clears them.
        assert {"van": "de bot"} in mm.update_props

    async def test_a_linked_account_gives_the_person_and_saves_a_call(
        self, db_session, create_person
    ):
        person = await create_person(naam="Persoon A")
        db_session.add(
            MattermostUser(
                person_id=person.id,
                mattermost_user_id=PERSOON_A,
                mattermost_username="persoon.a",
            )
        )
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)

        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_OPGEPAKT
        )
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert row.status_door_person_id == person.id
        assert _stand(mm.messages[row.thread_post_id]) == "👀 opgepakt door persoon.a"
        assert mm.username_reads == []

    async def test_a_name_that_cannot_be_found_is_left_out(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)

        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_OPGEPAKT
        )
        await _ronde(db_session, mm)

        # The fake gives the id back, as the real lookup does when it fails.
        assert _stand(mm.messages[markering.thread_post_id]) == "👀 opgepakt"
        assert PERSOON_A not in mm.messages[markering.thread_post_id]

    async def test_the_name_is_only_asked_for_when_it_is_shown(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)

        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        await _ronde(db_session, mm)

        assert mm.username_reads == []

    async def test_the_latest_reaction_by_anyone_decides(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id

        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
        await _ronde(db_session, mm)
        await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert (row.status, row.status_door_mattermost_user_id) == (
            STATUS_BEANTWOORD,
            PERSOON_B,
        )
        assert _stand(mm.messages[reply]) == "✅ beantwoord"

    async def test_the_same_status_by_someone_else_changes_who(self, db_session):
        mm = FakeMattermost()
        mm.usernames = {PERSOON_A: "persoon.a", PERSOON_B: "persoon.b"}
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id

        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
        await _ronde(db_session, mm)
        await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_OPGEPAKT)
        ronde = await _ronde(db_session, mm)

        assert ronde.gewijzigd == 1
        row = await _lees(db_session, markering.id)
        assert row.status_door_mattermost_user_id == PERSOON_B
        assert _stand(mm.messages[reply]) == "👀 opgepakt door persoon.b"

    async def test_the_hint_of_the_bot_is_not_an_answer(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        was = mm.messages[reply]
        mm.react(reply, BOT, REACTIE_HINT)
        await markeer_reactie(db_session, reply)
        await db_session.commit()

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd) == (1, 0)
        row = await _lees(db_session, markering.id)
        assert (row.status, row.status_at) == (STATUS_OPEN, None)
        assert mm.messages[reply] == was
        assert mm.updates == []

    async def test_another_emoji_changes_nothing(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        mm.react(markering.thread_post_id, PERSOON_A, "thumbsup")
        await markeer_reactie(db_session, markering.thread_post_id)
        await db_session.commit()

        await _ronde(db_session, mm)

        assert (await _lees(db_session, markering.id)).status == STATUS_OPEN
        assert mm.updates == []


NOOT = "_Citaten komen letterlijk uit het automatische transcript._"


class TestWatEenAntwoordAlZei:
    """The reply is written anew from the row. What it said when it was
    posted (the note under the first reply of a thread, the moment of the
    question) is on the row for that, and has to come back the same."""

    @pytest.mark.parametrize("met_noot", [True, False])
    @pytest.mark.parametrize(
        "emoji", [REACTIE_BEANTWOORD, REACTIE_OPGEPAKT, REACTIE_VERVALT]
    )
    async def test_a_status_keeps_the_note_or_keeps_lacking_it(
        self, db_session, met_noot, emoji
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id, met_noot=met_noot)
        reply = markering.thread_post_id
        assert (NOOT in mm.messages[reply]) is met_noot

        await _reageer(db_session, mm, reply, PERSOON_A, emoji)
        await _ronde(db_session, mm)

        assert _stand(mm.messages[reply]) != "❓"
        assert (NOOT in mm.messages[reply]) is met_noot
        assert mm.messages[reply].endswith(NOOT) is met_noot

    @pytest.mark.parametrize("met_noot", [True, False])
    async def test_a_rejected_reply_that_is_restored_is_what_it_was(
        self, db_session, met_noot
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id, met_noot=met_noot)
        reply = markering.thread_post_id
        was = mm.messages[reply]

        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_GEEN_VRAAG)
        await _ronde(db_session, mm)
        assert NOOT not in mm.messages[reply]
        await _haal_weg(db_session, mm, reply, PERSOON_A, REACTIE_GEEN_VRAAG)
        await _ronde(db_session, mm)

        assert mm.messages[reply] == was
        assert (NOOT in was) is met_noot
        # What the row says about the note is not touched by any of this.
        assert (await _lees(db_session, markering.id)).met_noot is met_noot

    async def test_the_moment_of_the_question_and_its_number_stay(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(
            db_session,
            mm,
            sessie_id,
            7,
            vraag_moment=MOMENT + timedelta(minutes=3),
            moment_url="https://debatdirect.example/debat?event=speaker",
            stuk="Voortgangsbrief voorbeelden",
        )
        reply = markering.thread_post_id
        was = mm.messages[reply]
        assert "Vraag 7 · aan de minister · [10:05](" in was

        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        assert mm.messages[reply] == was.replace("❓", "✅").replace(
            "Vraag 7 · ", "Vraag 7 · beantwoord · "
        )
        assert "📄 Voortgangsbrief voorbeelden" in mm.messages[reply]


class TestEenReactieWeghalen:
    async def test_taking_the_only_reaction_away_reopens_the_question(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        was = mm.messages[reply]
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_GEEN_VRAAG)
        await _ronde(db_session, mm)
        assert "\n" not in mm.messages[reply]
        voor = datetime.now(UTC)

        await _haal_weg(db_session, mm, reply, PERSOON_A, REACTIE_GEEN_VRAAG)
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert row.status == STATUS_OPEN
        assert row.status_door_mattermost_user_id is None
        # Nobody's reaction any more; when it was noticed is kept.
        assert row.status_at >= voor
        # The whole reply is back, quote and all: nothing was lost.
        assert mm.messages[reply] == was
        assert splits(mm.messages[row.beurt_post_id])[1] == ("❓ 1 vraag · 🔴 **open**")

    async def test_someone_elses_same_reaction_keeps_the_status(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        await _haal_weg(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert (row.status, row.status_door_mattermost_user_id) == (
            STATUS_BEANTWOORD,
            PERSOON_A,
        )
        assert _stand(mm.messages[reply]) == "✅ beantwoord"

    async def test_an_older_reaction_that_is_still_there_takes_over(self, db_session):
        mm = FakeMattermost()
        mm.usernames[PERSOON_A] = "persoon.a"
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
        await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        await _haal_weg(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert (row.status, row.status_door_mattermost_user_id) == (
            STATUS_TOEGEWEZEN,
            PERSOON_A,
        )
        assert _stand(mm.messages[reply]) == "👀 opgepakt door persoon.a"

    async def test_taking_away_an_old_reaction_changes_nothing(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
        await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)
        writes = len(mm.updates)

        await _haal_weg(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd) == (1, 0)
        assert (await _lees(db_session, markering.id)).status == STATUS_BEANTWOORD
        assert len(mm.updates) == writes


class TestHetStatusblok:
    async def test_counts_the_questions_of_a_turn_per_state(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        een = await _markering(db_session, mm, sessie_id, 1)
        beurt = een.beurt_post_id
        twee = await _markering(db_session, mm, sessie_id, 2, beurt_post_id=beurt)
        drie = await _markering(db_session, mm, sessie_id, 3, beurt_post_id=beurt)
        assert splits(mm.messages[beurt])[1] == "❓ 3 vragen · 🔴 **open**"

        await _reageer(
            db_session, mm, twee.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        await _reageer(
            db_session, mm, drie.thread_post_id, PERSOON_A, REACTIE_GEEN_VRAAG
        )
        await _ronde(db_session, mm)

        assert splits(mm.messages[beurt]) == (
            TURN,
            "❓ 2 vragen · 🔴 **1 open** · 1 beantwoord",
        )

    async def test_is_gone_when_every_question_of_the_turn_was_rejected(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        een = await _markering(db_session, mm, sessie_id, 1)
        beurt = een.beurt_post_id
        twee = await _markering(db_session, mm, sessie_id, 2, beurt_post_id=beurt)

        for markering in (een, twee):
            await _reageer(
                db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_GEEN_VRAAG
            )
        await _ronde(db_session, mm)

        # No rule, no block: the message is the turn again.
        assert mm.messages[beurt] == TURN

    async def test_comes_back_when_a_rejection_is_taken_back(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply, beurt = markering.thread_post_id, markering.beurt_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_GEEN_VRAAG)
        await _ronde(db_session, mm)
        assert mm.messages[beurt] == TURN

        await _haal_weg(db_session, mm, reply, PERSOON_A, REACTIE_GEEN_VRAAG)
        await _ronde(db_session, mm)

        assert splits(mm.messages[beurt])[1] == "❓ 1 vraag · 🔴 **open**"

    async def test_keeps_a_transcript_that_grew_meanwhile(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        beurt = markering.beurt_post_id
        mm.messages[beurt] = mm.messages[beurt].replace(
            "een vraag.", "een vraag. En nog een zin."
        )

        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        await _ronde(db_session, mm)

        body, blok = splits(mm.messages[beurt])
        assert body.endswith("En nog een zin.")
        assert blok == "❓ 1 vraag · beantwoord"


class TestBegrensd:
    async def test_nothing_marked_costs_no_call_to_mattermost(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        await _markering(db_session, mm, sessie_id)

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (0, 0)
        assert mm.reaction_reads == mm.reads == []

    async def test_a_burst_of_clicks_is_one_write_per_message(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id

        for _ in range(10):
            await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
            await _haal_weg(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)
            await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
            await _haal_weg(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)
        await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_VERVALT)
        await _ronde(db_session, mm)

        assert mm.reaction_reads == [reply]
        assert sorted(post_id for post_id, _ in mm.updates) == sorted(
            [reply, markering.beurt_post_id]
        )

    async def test_once_worked_in_it_is_not_looked_at_again(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        await _ronde(db_session, mm)
        reads = len(mm.reads) + len(mm.reaction_reads)

        await _ronde(db_session, mm)

        assert len(mm.reads) + len(mm.reaction_reads) == reads

    async def test_the_same_click_heard_twice_writes_nothing_twice(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)
        writes = list(mm.updates)
        sinds = (await _lees(db_session, markering.id)).status_at

        await markeer_reactie(db_session, reply)
        await db_session.commit()
        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd) == (1, 0)
        assert mm.updates == writes
        row = await _lees(db_session, markering.id)
        assert (row.status_at, row.reacties_gewijzigd_at) == (sinds, None)

    async def test_a_round_takes_no_more_than_its_share(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        aantal = MAX_PER_RONDE + 3
        for nummer in range(1, aantal + 1):
            markering = await _markering(db_session, mm, sessie_id, nummer)
            await _reageer(
                db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
            )

        eerste = await _ronde(db_session, mm)
        tweede = await _ronde(db_session, mm)

        assert eerste.bijgewerkt == MAX_PER_RONDE
        assert tweede.bijgewerkt == 3


class TestMattermostFaalt:
    async def test_reactions_that_cannot_be_read_wait_for_the_next_round(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        mm.fail_reactions = 1

        ronde = await _ronde(db_session, mm)

        # Not read is not "no reactions": the question does not reopen.
        assert (ronde.bijgewerkt, ronde.mislukt) == (0, 1)
        row = await _lees(db_session, markering.id)
        assert row.status == STATUS_OPEN
        assert row.reacties_gewijzigd_at is not None
        assert mm.updates == []

        assert (await _ronde(db_session, mm)).bijgewerkt == 1
        assert (await _lees(db_session, markering.id)).status == STATUS_BEANTWOORD

    async def test_unread_reactions_do_not_reopen_an_answered_question(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)

        await markeer_reactie(db_session, reply)
        await db_session.commit()
        mm.fail_reactions = 1
        await _ronde(db_session, mm)

        assert (await _lees(db_session, markering.id)).status == STATUS_BEANTWOORD
        assert _stand(mm.messages[reply]) == "✅ beantwoord"

    async def test_a_reply_that_fails_alone_keeps_the_mark(self, db_session):
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))
        reply, beurt = markering.thread_post_id, markering.beurt_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        # The reply is written first: only that write fails.
        mm.fail_updates = 1

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (0, 1)
        assert [post_id for post_id, _ in mm.updates] == [beurt]
        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at is not None

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (1, 0)
        assert _stand(mm.messages[reply]) == "✅ beantwoord"
        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at is None

    async def test_the_newest_reactions_go_first(self, db_session, monkeypatch):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        oud = await _markering(db_session, mm, sessie_id, 1)
        nieuw = await _markering(db_session, mm, sessie_id, 2)
        await _reageer(db_session, mm, oud.thread_post_id, PERSOON_A, REACTIE_OPGEPAKT)
        await _reageer(
            db_session, mm, nieuw.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        monkeypatch.setattr(mod, "MAX_PER_RONDE", 1)

        await _ronde(db_session, mm)

        # Who clicked last is served first; a row that keeps failing can
        # then never hold up the ones that came after it.
        assert (await _lees(db_session, nieuw.id)).status == STATUS_BEANTWOORD
        assert (await _lees(db_session, oud.id)).status == STATUS_OPEN

    @pytest.mark.parametrize("hoe", ["fail_updates", "raise_updates", "fail_reads"])
    async def test_a_write_that_fails_is_made_up_for(self, db_session, hoe):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply, beurt = markering.thread_post_id, markering.beurt_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        # Both the reply and the status block fail this round.
        setattr(mm, hoe, 2)

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd, ronde.mislukt) == (0, 1, 1)
        row = await _lees(db_session, markering.id)
        # What was said is stored; only the channel is behind.
        assert row.status == STATUS_BEANTWOORD
        assert row.reacties_gewijzigd_at is not None
        assert row.statusregel_at is None
        assert mm.updates == []

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd, ronde.mislukt) == (1, 0, 0)
        assert _stand(mm.messages[reply]) == "✅ beantwoord"
        assert splits(mm.messages[beurt])[1] == "❓ 1 vraag · beantwoord"
        row = await _lees(db_session, markering.id)
        assert row.reacties_gewijzigd_at is None
        assert row.statusregel_at is not None

    async def test_a_status_block_that_fails_alone_keeps_the_mark(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)

        async def update_post(post_id, message, props=None):
            if post_id == reply:
                mm.messages[post_id] = message
                return True
            return False

        mm.update_post = update_post
        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (0, 1)
        row = await _lees(db_session, markering.id)
        assert row.reacties_gewijzigd_at is not None
        assert row.statusregel_at is None

    async def test_without_knowing_the_bot_nothing_is_derived(self, db_session):
        """The bot puts a ✅ under every reply. Not knowing which reactions
        are its own would turn every question into an answered one."""
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        mm.react(reply, BOT, REACTIE_HINT)
        await markeer_reactie(db_session, reply)
        await db_session.commit()
        mm.bot = None

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (0, 1)
        assert mm.reaction_reads == []
        row = await _lees(db_session, markering.id)
        assert row.status == STATUS_OPEN
        assert row.reacties_gewijzigd_at is not None

    async def test_mattermost_switched_off_is_left_alone(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        mm.enabled = False

        await _ronde(db_session, mm)

        assert mm.reaction_reads == []
        assert (await _lees(db_session, markering.id)).status == STATUS_OPEN

    async def test_a_reply_that_was_deleted_is_let_go(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)
        await _ronde(db_session, mm)
        await markeer_reactie(db_session, reply)
        await db_session.commit()
        mm.gone.add(reply)

        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (1, 0)
        row = await _lees(db_session, markering.id)
        # The status stays what it was, and it is not asked for again.
        assert row.status == STATUS_BEANTWOORD
        assert row.reacties_gewijzigd_at is None

    async def test_a_reply_deleted_after_its_reactions_were_read_is_let_go_too(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply, beurt = markering.thread_post_id, markering.beurt_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)

        async def get_post(post_id):
            if post_id == reply:
                raise PostNotFoundError(post_id)
            return {"id": post_id, "message": mm.messages[post_id], "props": {}}

        mm.get_post = get_post
        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (1, 0)
        row = await _lees(db_session, markering.id)
        assert row.reacties_gewijzigd_at is None
        # The turn still says what became of its question.
        assert splits(mm.messages[beurt])[1] == "❓ 1 vraag · beantwoord"

    async def test_a_turn_that_was_deleted_does_not_keep_the_reply_waiting(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)

        async def get_post(post_id):
            if post_id != reply:
                raise PostNotFoundError(post_id)
            return {"id": post_id, "message": mm.messages[post_id], "props": {}}

        mm.get_post = get_post
        ronde = await _ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (1, 0)
        assert _stand(mm.messages[reply]) == "✅ beantwoord"

    async def test_after_an_hour_it_is_given_up(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )
        straks = datetime.now(UTC) + GEEF_OP_NA

        nog_net = await _ronde(db_session, mm, now=straks - timedelta(minutes=1))
        assert nog_net.bijgewerkt == 1

        await markeer_reactie(db_session, markering.thread_post_id)
        await db_session.commit()
        reads = len(mm.reaction_reads)
        te_laat = await _ronde(db_session, mm, now=straks + timedelta(minutes=1))

        assert (te_laat.bijgewerkt, te_laat.mislukt) == (0, 0)
        assert len(mm.reaction_reads) == reads


@pytest.fixture
async def savepoints(_test_engine):
    """A session whose rollback undoes only what was not committed.

    With `db_session` a rollback by the service takes the whole test with
    it, and a session that really commits would leave a marked markering
    in the database for the rounds of tests that run next to this one.
    Here a commit is a savepoint that is kept, and nothing leaves the test.
    """
    async with _test_engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()


class TestEenMarkeringDieOmvalt:
    async def test_does_not_stop_the_others(self, savepoints):
        session = savepoints
        mm = FakeMattermost()
        sessie_id = await _sessie(session)
        een = await _markering(session, mm, sessie_id, 1)
        twee = await _markering(session, mm, sessie_id, 2)
        for markering in (een, twee):
            await _reageer(
                session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
            )
        kapot, heel, heel_id = een.thread_post_id, twee.thread_post_id, twee.id
        echte = mm.get_post_reactions

        async def get_post_reactions(post_id):
            if post_id == kapot:
                raise RuntimeError("valt om")
            return await echte(post_id)

        mm.get_post_reactions = get_post_reactions
        ronde = await _ronde(session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (1, 1)
        assert _stand(mm.messages[heel]) == "✅ beantwoord"
        assert (await _lees(session, heel_id)).status == STATUS_BEANTWOORD


class TestEenReactieTijdensDeRonde:
    async def test_a_click_during_the_round_is_not_lost(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_OPGEPAKT)

        async def on_read(post_id):
            # While the reply is being rewritten, someone answers.
            mm.on_read = None
            await asyncio.sleep(0.01)
            await _reageer(db_session, mm, reply, PERSOON_B, REACTIE_BEANTWOORD)

        mm.on_read = on_read
        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert row.status == STATUS_TOEGEWEZEN
        # The mark is the newer one, so the next round takes it up.
        assert row.reacties_gewijzigd_at is not None

        await _ronde(db_session, mm)

        row = await _lees(db_session, markering.id)
        assert row.status == STATUS_BEANTWOORD
        assert row.reacties_gewijzigd_at is None
        assert _stand(mm.messages[reply]) == "✅ beantwoord"


@pytest.fixture
async def real(_test_engine):
    """Sessions that really commit, and a debate that is cleaned up after.

    `db_session` is one connection in one transaction: a row it locks is
    never locked for itself, so it cannot show one session waiting for
    another.
    """
    sessions: list[AsyncSession] = []
    sessie_ids: list[uuid.UUID] = []

    def new_session() -> AsyncSession:
        session = AsyncSession(bind=_test_engine, expire_on_commit=False)
        sessions.append(session)
        return session

    async def new_sessie() -> uuid.UUID:
        session = new_session()
        sessie_id = await _sessie(session)
        await session.commit()
        sessie_ids.append(sessie_id)
        return sessie_id

    try:
        yield new_session, new_sessie
    finally:
        for session in sessions:
            await session.rollback()
            await session.close()
        cleanup = AsyncSession(bind=_test_engine)
        await cleanup.execute(delete(DebatSessie).where(DebatSessie.id.in_(sessie_ids)))
        await cleanup.commit()
        await cleanup.close()


class TestRealSessions:
    async def test_the_websocket_never_waits_for_a_round(self, real):
        """While the round is asking Mattermost for a message, a reaction
        comes in on the same reply. Its mark has to land at once: the
        websocket reads every event of every channel in one loop.

        The mark of the websocket is not committed here, and the round is
        asked for this one markering: a marked markering that is really in
        the database would be picked up by the rounds of other tests.
        """
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        markering = await _markering(new_session(), mm, sessie_id)
        reply = markering.thread_post_id
        mm.react(reply, PERSOON_A, REACTIE_OPGEPAKT)
        websocket = new_session()
        landed: list[bool] = []

        async def on_read(post_id):
            mm.on_read = None
            landed.append(
                await asyncio.wait_for(markeer_reactie(websocket, reply), timeout=5)
            )
            await websocket.rollback()

        mm.on_read = on_read
        svc = DebatVraagStatusService(new_session(), mm)
        klaar, gewijzigd = await asyncio.wait_for(
            svc._werk_een_bij(markering.id, datetime.now(UTC), BOT, datetime.now(UTC)),
            timeout=20,
        )

        assert landed == [True]
        assert (klaar, gewijzigd) == (True, True)
        # What the round stored was committed before it went to Mattermost.
        row = await _lees(new_session(), markering.id)
        assert row.status == STATUS_TOEGEWEZEN
        assert _stand(mm.messages[reply]) == "👀 opgepakt"


# --- what a rejected markering is kept for ------------------------------


class TestVerworpenBewaard:
    async def test_rejected_markeringen_can_be_listed_with_what_was_marked(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        andere_sessie = await _sessie(db_session)
        een = await _markering(db_session, mm, sessie_id, 1)
        twee = await _markering(db_session, mm, sessie_id, 2)
        await _markering(db_session, mm, sessie_id, 3)
        elders = await _markering(db_session, mm, andere_sessie, 1)
        for markering in (een, twee, elders):
            await _reageer(
                db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_GEEN_VRAAG
            )
        await _reageer(db_session, mm, twee.thread_post_id, PERSOON_B, REACTIE_VERVALT)
        await _ronde(db_session, mm)

        rows = await verworpen_markeringen(db_session, sessie_id=sessie_id)

        # Only what is rejected now, and only of this debate.
        assert [r.id for r in rows] == [een.id]
        assert rows[0].citaat == "Wanneer komt brief 1 naar de Kamer?"
        assert rows[0].samenvatting == "Wanneer brief 1 komt."
        assert rows[0].status_door_mattermost_user_id == PERSOON_A
        assert rows[0].status_at is not None
        alle = await verworpen_markeringen(db_session)
        assert {een.id, elders.id} <= {r.id for r in alle}
        assert twee.id not in {r.id for r in alle}

    async def test_newest_first_and_no_more_than_asked(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markeringen = [
            await _markering(db_session, mm, sessie_id, n) for n in (1, 2, 3)
        ]
        for markering in markeringen:
            await _reageer(
                db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_GEEN_VRAAG
            )
        await _ronde(db_session, mm)

        rows = await verworpen_markeringen(db_session, sessie_id=sessie_id, limit=2)

        assert [r.id for r in rows] == [markeringen[2].id, markeringen[1].id]


# --- the model's list of open questions ---------------------------------


class FakeLLM:
    pass


class TestWatHetModelNogOpenZiet:
    async def test_picked_up_is_still_open_answered_and_rejected_are_not(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        statussen = [
            STATUS_OPEN,
            STATUS_TOEGEWEZEN,
            STATUS_BEANTWOORD,
            STATUS_VERVALT,
            STATUS_VERWORPEN,
        ]
        for nummer, status in enumerate(statussen, start=1):
            await _markering(db_session, mm, sessie_id, nummer, status=status)

        svc = DebatVraagService(db_session, mm, FakeLLM())
        nummers = [r[0] for r in await svc._openstaand(sessie_id, "Kamerlid A (X)")]

        assert nummers == [1, 2]


# --- a new reply ---------------------------------------------------------


class TestEenNieuweThread:
    async def test_gets_one_reaction_of_the_bot_to_click_on(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id, thread_post_id=None)

        svc = DebatVraagService(db_session, mm, FakeLLM())
        assert await svc._post_thread(markering.id) is True

        reply = (await _lees(db_session, markering.id)).thread_post_id
        assert mm.reactions[reply] == [_reactie(BOT, "white_check_mark", 2_000)]

    async def test_a_reaction_that_cannot_be_put_does_not_undo_the_thread(
        self, db_session
    ):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id, thread_post_id=None)

        async def add_reaction(post_id, emoji):
            raise RuntimeError("mattermost is weg")

        mm.add_reaction = add_reaction
        svc = DebatVraagService(db_session, mm, FakeLLM())

        assert await svc._post_thread(markering.id) is True
        assert (await _lees(db_session, markering.id)).thread_post_id is not None

    async def test_a_thread_that_was_not_posted_gets_no_reaction(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id, thread_post_id=None)

        async def send_channel_message(*args, **kwargs):
            return None

        mm.send_channel_message = send_channel_message
        svc = DebatVraagService(db_session, mm, FakeLLM())

        assert await svc._post_thread(markering.id) is False
        assert mm.reactions == {}


# --- the websocket -------------------------------------------------------


def _event(event: str, user: str, post_id: str, emoji: str, *, as_json=True) -> dict:
    reaction = {"user_id": user, "post_id": post_id, "emoji_name": emoji}
    return {
        "event": event,
        "data": {"reaction": json.dumps(reaction) if as_json else reaction},
    }


@pytest.fixture
def websocket(db_session, monkeypatch):
    """The websocket service on the session of the test, and what else it
    did with a reaction: the paths for an alert and a suggested lead."""
    opened: list[bool] = []

    @asynccontextmanager
    async def _session():
        opened.append(True)
        yield db_session

    monkeypatch.setattr(ws_mod, "async_session", _session)
    svc = ws_mod.MattermostWebsocketService()
    svc._bot_user_id = BOT
    elders: list[tuple[str, str]] = []

    async def _kamerstuk(post_id, emoji_name):
        elders.append((post_id, emoji_name))
        return True

    monkeypatch.setattr(svc, "_verwerk_kamerstuk_reactie", _kamerstuk)
    return svc, opened, elders


class TestDeWebsocket:
    @pytest.mark.parametrize("event", ["reaction_added", "reaction_removed"])
    @pytest.mark.parametrize(
        "emoji",
        [REACTIE_BEANTWOORD, REACTIE_OPGEPAKT, REACTIE_VERVALT, REACTIE_GEEN_VRAAG],
    )
    async def test_a_reaction_on_a_reply_marks_the_markering(
        self, db_session, websocket, monkeypatch, event, emoji
    ):
        svc, _, elders = websocket
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        andere = await _markering(db_session, mm, sessie_id, 2)
        voor = datetime.now(UTC)
        commits: list[bool] = []
        echte_commit = db_session.commit

        async def commit():
            commits.append(True)
            await echte_commit()

        monkeypatch.setattr(db_session, "commit", commit)

        await svc._dispatch(_event(event, PERSOON_A, markering.thread_post_id, emoji))

        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at >= voor
        # The round that works it in is another session: it has to be
        # committed, and nobody else does that for the websocket.
        assert commits == [True]
        # Only this one, and nothing else is tried with the same emoji.
        assert (await _lees(db_session, andere.id)).reacties_gewijzigd_at is None
        assert elders == []
        # Nothing is written to the channel from the websocket.
        assert mm.reads == mm.reaction_reads == mm.updates == []

    async def test_the_reaction_as_a_dict_is_read_too(self, db_session, websocket):
        svc, _, _ = websocket
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))

        await svc._dispatch(
            _event(
                "reaction_removed",
                PERSOON_A,
                markering.thread_post_id,
                REACTIE_BEANTWOORD,
                as_json=False,
            )
        )

        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at

    @pytest.mark.parametrize("event", ["reaction_added", "reaction_removed"])
    async def test_the_bots_own_reaction_is_not_even_looked_up(
        self, db_session, websocket, event
    ):
        svc, opened, _ = websocket
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))

        await svc._dispatch(
            _event(event, BOT, markering.thread_post_id, REACTIE_BEANTWOORD)
        )

        assert opened == []
        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at is None

    @pytest.mark.parametrize("event", ["reaction_added", "reaction_removed"])
    async def test_without_knowing_the_bot_nothing_is_marked(
        self, db_session, websocket, event
    ):
        svc, opened, _ = websocket
        svc._bot_user_id = None
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))

        await svc._dispatch(
            _event(event, PERSOON_A, markering.thread_post_id, REACTIE_BEANTWOORD)
        )

        assert opened == []

    @pytest.mark.parametrize("event", ["reaction_added", "reaction_removed"])
    async def test_another_emoji_costs_no_lookup(self, db_session, websocket, event):
        svc, opened, _ = websocket
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))

        await svc._dispatch(
            _event(event, PERSOON_A, markering.thread_post_id, "thumbsup")
        )

        assert opened == []
        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at is None

    async def test_a_reaction_on_another_message_goes_on_to_what_it_meant(
        self, db_session, websocket
    ):
        svc, opened, elders = websocket
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))

        # The message of the turn is not the reply.
        await svc._dispatch(
            _event(
                "reaction_added", PERSOON_A, markering.beurt_post_id, REACTIE_GEEN_VRAAG
            )
        )

        assert opened == [True]
        assert (await _lees(db_session, markering.id)).reacties_gewijzigd_at is None
        assert elders == [(markering.beurt_post_id, "x")]

    async def test_taking_a_reaction_off_another_message_does_nothing(
        self, db_session, websocket
    ):
        svc, opened, elders = websocket

        await svc._dispatch(
            _event("reaction_removed", PERSOON_A, "eenanderepost", REACTIE_GEEN_VRAAG)
        )

        # One lookup, and no button is pressed by letting go of it.
        assert opened == [True]
        assert elders == []

    @pytest.mark.parametrize("event", ["reaction_added", "reaction_removed"])
    async def test_a_database_that_is_away_does_not_reach_the_read_loop(
        self, db_session, websocket, monkeypatch, event
    ):
        svc, _, elders = websocket

        async def kapot(session, post_id):
            raise RuntimeError("database is weg")

        monkeypatch.setattr(mod, "markeer_reactie", kapot)

        await svc._dispatch(_event(event, PERSOON_A, "eenpost", REACTIE_GEEN_VRAAG))

        # Not handled here, so an alert still gets its click.
        assert elders == ([("eenpost", "x")] if event == "reaction_added" else [])

    async def test_a_session_that_cannot_be_opened_does_not_either(
        self, websocket, monkeypatch
    ):
        svc, _, _ = websocket

        def kapot():
            raise RuntimeError("geen verbinding")

        monkeypatch.setattr(ws_mod, "async_session", kapot)

        assert await svc._handle_vraag_reactie("eenpost", REACTIE_GEEN_VRAAG) is False

    @pytest.mark.parametrize(
        "data",
        [{}, {"reaction": "geen json"}, {"reaction": json.dumps({"post_id": "p"})}],
    )
    async def test_a_removal_that_cannot_be_read_is_dropped(self, websocket, data):
        svc, opened, _ = websocket

        await svc._dispatch({"event": "reaction_removed", "data": data})

        assert opened == []


# --- the round of the questions ------------------------------------------


class TestDeRondeVanDeVragen:
    async def test_works_reactions_in_also_when_no_debate_is_running(self, db_session):
        mm = FakeMattermost()
        sessie_id = await _sessie(db_session)
        markering = await _markering(db_session, mm, sessie_id)
        await _reageer(
            db_session, mm, markering.thread_post_id, PERSOON_A, REACTIE_BEANTWOORD
        )

        result = await DebatVraagWorker(db_session, mm, llm=None).tick()

        assert result.fouten == 0
        assert (await _lees(db_session, markering.id)).status == STATUS_BEANTWOORD
        assert _stand(mm.messages[markering.thread_post_id]) == "✅ beantwoord"

    async def test_reactions_that_take_too_long_do_not_hold_up_the_round(
        self, db_session, monkeypatch
    ):
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))
        # Read now: the round rolls back, and the object is stale after.
        reply = markering.thread_post_id
        await _reageer(db_session, mm, reply, PERSOON_A, REACTIE_BEANTWOORD)

        begonnen = []

        async def traag(post_id):
            begonnen.append(post_id)
            await asyncio.sleep(30)

        monkeypatch.setattr(mm, "get_post_reactions", traag)
        monkeypatch.setattr(debat_vraag_worker, "REACTIES_BUDGET", 0.05)

        # Without the limit this takes the half minute of the slow call.
        result = await asyncio.wait_for(
            DebatVraagWorker(db_session, mm, llm=None).tick(), timeout=5
        )

        assert begonnen == [reply]
        assert result.fouten == 0
        # The reply was not touched; the mark is cleared only after a round
        # that wrote everything, so this one is tried again.
        assert mm.updates == []

    async def test_reactions_that_break_do_not_stop_the_round(
        self, db_session, monkeypatch
    ):
        async def kapot(self, now=None):
            raise RuntimeError("valt om")

        monkeypatch.setattr(DebatVraagStatusService, "werk_bij", kapot)

        result = await DebatVraagWorker(db_session, FakeMattermost(), llm=None).tick()

        assert result.fouten == 0


class TestDeKolommen:
    async def test_a_markering_nobody_reacted_to_has_no_status_history(
        self, db_session
    ):
        mm = FakeMattermost()
        markering = await _markering(db_session, mm, await _sessie(db_session))

        row = await _lees(db_session, markering.id)

        assert row.status == STATUS_OPEN
        assert (
            row.status_at,
            row.status_door_mattermost_user_id,
            row.status_door_person_id,
            row.reacties_gewijzigd_at,
        ) == (None, None, None, None)
