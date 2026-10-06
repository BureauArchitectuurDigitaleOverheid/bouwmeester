"""Tests for reading a turn for questions only once its text is final.

Around a change of speaker the voices decide whose a line is, and a line
can go to the turn before or after. A turn read before that leaves a
thread under the wrong speaker. Here a whole debate is played with the
timeline, the subtitles, the made-up audio of the voice tests and a model
that marks one sentence, to see under whose message the thread ends up and
when; and rows written by hand, for exactly which line holds which turn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select, update

from bouwmeester.core.config import get_settings
from bouwmeester.models.debat_sessie import (
    TOEWIJZING_STEM,
    DebatOndertitel,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_stem as stem
from bouwmeester.services import debat_stemmen_service as svc
from bouwmeester.services import debat_vraag_worker as mod
from bouwmeester.services.debat_stemmen_service import (
    AFTER,
    BEFORE,
    RETRY_FOR,
    WAIT,
    DebatStemmen,
    as_turns,
    message_of,
)
from bouwmeester.services.debat_tijdlijn_service import DebatTijdlijnService
from bouwmeester.services.debat_transcript_service import AFTER_END
from bouwmeester.services.debat_vraag_worker import (
    MARGIN,
    NEVER_MOVES_AFTER,
    REACH,
    DebatVraagWorker,
    rows_in_play,
    text_is_complete,
    voices_listen,
)
from tests.test_debat_stemmen import AUDIO, Sound, _where, _with_audio
from tests.test_debat_tijdlijn import START, Feed, _debat, _sessie
from tests.test_debat_transcript import OFFSET, Subtitles, _cue, _stream
from tests.test_debat_vraag_worker import (
    OPENING,
    PART,
    Q_BUDGET,
    Q_WANNEER,
    Chat,
    Outside,
    _at,
    _in_channel,
    _row,
    _running,
    _tick,
)
from tests.test_debat_vragen import FakeLLM, antwoord, vraag

# A speaker, an interruption, the answer and the next speaker. The events
# are off the way they are in a real debate: the interruption is entered 8
# seconds before the interrupter says a word, the answer 10 seconds after
# it began.
EVENTS = (
    ("speaker", 1, "a"),
    ("interrupter", 3, "b"),
    ("speaker", 4, "a"),
    ("speaker", 6, "c"),
)
SPEAKING = [(60, 1), (188, 2), (230, 1), (360, 3)]
# The last sentence of the speaker before the interruption. By the time
# alone it is under the interruption.
ASKED_AT = 186


class Marks(FakeLLM):
    """A model that finds the one question, in whatever turn it is."""

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        if Q_WANNEER in prompt:
            return antwoord(vraag(Q_WANNEER))
        return antwoord()


def _cues(first: int = 62, last: int = 418):
    return [
        _cue(s, Q_WANNEER if s == ASKED_AT else f"r{s}.", 3.0)
        for s in range(first, last + 1, 4)
    ]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Nothing in the memory of the process is left from another test."""
    stem.VOICES.clear()
    mod._pause.reset()
    monkeypatch.setattr(stem, "_loaded", {})
    yield
    stem.VOICES.clear()
    mod._pause.reset()


def _model(monkeypatch, embedder) -> None:
    """What the process knows about the model, as after the first load."""
    monkeypatch.setitem(stem._loaded, get_settings().DEBAT_STEM_MODEL_PATH, embedder)


class Debate:
    """A debate with audio, followed by the timeline and the marking."""

    def __init__(self, db_session, monkeypatch, events=EVENTS, audio=True) -> None:
        self.db = db_session
        part = _debat(*events)
        self.feed = Feed(
            monkeypatch, parts=[_with_audio(part) if audio else _stream(part)]
        )
        Outside(monkeypatch)
        self.track = Subtitles(monkeypatch, self.feed, _cues())
        self.sound = Sound(monkeypatch, self.feed, SPEAKING)
        _model(monkeypatch, self.sound.embedder)
        self.mm = Chat()
        self.llm = Marks()
        self.at = -600.0

    async def play(self, until: float, step: int = 10) -> None:
        """Up to and including this many seconds after the start."""
        while self.at <= until:
            now = START + timedelta(seconds=self.at)
            self.feed.now = now
            await DebatTijdlijnService(self.db, self.mm).tick(now.astimezone(UTC))
            await DebatVraagWorker(self.db, self.mm, self.llm).tick(now.astimezone(UTC))
            self.at += step

    async def read(self) -> dict[str, int]:
        """Per turn that was read: how many seconds after the start."""
        rows = await self.db.execute(
            select(
                DebatSpreekbeurt.object_id,
                DebatSpreekbeurt.event_start,
                DebatSpreekbeurt.beoordeeld_at,
            ).where(DebatSpreekbeurt.beoordeeld_at.is_not(None))
        )
        return {
            f"{who}@{round((start - START).total_seconds())}": round(
                (at - START).total_seconds()
            )
            for who, start, at in rows.all()
        }

    async def post_of(self, who: str, seconds: int) -> str:
        return (
            await self.db.execute(
                select(DebatSpreekbeurt.post_id).where(
                    DebatSpreekbeurt.object_id == who,
                    DebatSpreekbeurt.event_start == START + timedelta(seconds=seconds),
                )
            )
        ).scalar_one()

    async def threads(self) -> list[str]:
        """Who each thread hangs under, as who@seconds."""
        rows = await self.db.execute(
            select(
                DebatSpreekbeurt.object_id,
                DebatSpreekbeurt.event_start,
                DebatSpreekbeurt.post_id,
            ).where(DebatSpreekbeurt.post_id.is_not(None))
        )
        names = {
            post_id: f"{who}@{round((start - START).total_seconds())}"
            for who, start, post_id in rows.all()
        }
        return [names[root] for root, _ in self.mm.threads]


@pytest.mark.asyncio
class TestAQuestionAtTheEdge:
    """A whole debate: under whose message the thread ends up, and when."""

    async def test_the_thread_is_under_who_asked_and_as_soon_as_the_lines_are_decided(
        self, db_session, monkeypatch
    ):
        debate = Debate(db_session, monkeypatch)
        sessie = await _sessie(db_session)

        await debate.play(480)

        where = await _where(db_session, sessie)
        assert where[Q_WANNEER] == ("speaker", "a", 60, TOEWIJZING_STEM, True)
        assert await debate.threads() == ["a@60"]
        assert Q_WANNEER in debate.mm.messages[await debate.post_of("a", 60)]
        assert Q_WANNEER not in debate.mm.messages[await debate.post_of("b", 180)]
        # A minute after the interruption began: the subtitles are 35
        # seconds behind, and the voices had decided by then. No later
        # than a turn was read before lines were waited for.
        assert await debate.read() == {"a@60": 240, "b@180": 300, "a@240": 420}

    async def test_a_voice_that_is_known_minutes_later_is_waited_for(
        self, db_session, monkeypatch
    ):
        """The audio is away when the turns end and back five minutes
        later. Read at once, the question is found in the interruption,
        and the thread hangs there after the sentence has gone back to
        who said it."""
        debate = Debate(db_session, monkeypatch)
        sessie = await _sessie(db_session)
        debate.sound.down = True

        await debate.play(400)

        assert await debate.read() == {}
        assert debate.mm.threads == []
        assert debate.llm.prompts == []

        debate.sound.down = False
        await debate.play(600)

        where = await _where(db_session, sessie)
        assert where[Q_WANNEER] == ("speaker", "a", 60, TOEWIJZING_STEM, True)
        assert await debate.threads() == ["a@60"]
        assert Q_WANNEER in debate.mm.messages[await debate.post_of("a", 60)]
        assert Q_WANNEER not in debate.mm.messages[await debate.post_of("b", 180)]
        # The round the voices decided in, not one later.
        assert (await debate.read())["a@60"] == 410

    async def test_without_a_model_a_turn_is_read_as_promptly_as_ever(
        self, db_session, monkeypatch
    ):
        """No line is ever marked as decided then. Nothing waits for it."""
        debate = Debate(db_session, monkeypatch)
        debate.sound.embedder = None
        _model(monkeypatch, None)
        sessie = await _sessie(db_session)

        await debate.play(480)

        where = await _where(db_session, sessie)
        assert not any(done for *_, done in where.values())
        assert await debate.read() == {"a@60": 240, "b@180": 300, "a@240": 420}
        # Where the time put the sentence, as it was before voices.
        assert await debate.threads() == ["b@180"]

    async def test_with_the_voices_switched_off_a_turn_is_read_as_promptly_as_ever(
        self, db_session, monkeypatch
    ):
        debate = Debate(db_session, monkeypatch)
        monkeypatch.setattr(get_settings(), "DEBAT_STEMMEN_ENABLED", False)
        sessie = await _sessie(db_session)

        await debate.play(480)

        where = await _where(db_session, sessie)
        assert not any(done for *_, done in where.values())
        assert await debate.read() == {"a@60": 240, "b@180": 300, "a@240": 420}

    async def test_a_part_without_audio_is_read_as_promptly_as_ever(
        self, db_session, monkeypatch
    ):
        debate = Debate(db_session, monkeypatch, audio=False)
        sessie = await _sessie(db_session)

        await debate.play(480)

        where = await _where(db_session, sessie)
        assert not any(done for *_, done in where.values())
        assert await debate.read() == {"a@60": 240, "b@180": 300, "a@240": 420}

    async def test_audio_that_never_comes_does_not_keep_a_turn_waiting_for_ever(
        self, db_session, monkeypatch
    ):
        debate = Debate(db_session, monkeypatch)
        debate.sound.down = True
        sessie = await _sessie(db_session)

        await debate.play(780)
        assert await debate.read() == {}

        await debate.play(1000)

        # The voices give up on a line ten minutes after it was said, and
        # that is the round the turns around it are read in.
        read = await debate.read()
        given_up = ASKED_AT + RETRY_FOR.total_seconds()
        assert given_up < read["a@60"] <= given_up + 10
        assert set(read) == {"a@60", "b@180", "a@240"}
        where = await _where(db_session, sessie)
        assert where[Q_WANNEER] == ("interrupter", "b", 180, "tijd", True)
        assert await debate.threads() == ["b@180"]

    async def test_lines_nobody_ever_settles_do_not_keep_a_turn_waiting_for_ever(
        self, db_session, monkeypatch
    ):
        """The step that decides breaks on every round, so no line is
        marked. Past the moment the voices would not move a line any
        more, it counts as staying where it is."""
        debate = Debate(db_session, monkeypatch)
        sessie = await _sessie(db_session)

        async def broken(self, *args, **kwargs):
            raise RuntimeError("stuk")

        monkeypatch.setattr(DebatStemmen, "update", broken)

        await debate.play(840)
        assert await debate.read() == {}

        await debate.play(1040)

        where = await _where(db_session, sessie)
        assert not any(done for *_, done in where.values())
        read = await debate.read()
        cap = ASKED_AT + NEVER_MOVES_AFTER.total_seconds()
        assert cap < read["a@60"] <= cap + 10
        assert set(read) == {"a@60", "b@180", "a@240"}

    async def test_after_a_restart_the_lines_that_wait_are_still_waited_for(
        self, db_session, monkeypatch
    ):
        """The voices are gone from memory and nobody has looked for the
        model yet. The lines kept from before can still move."""
        debate = Debate(db_session, monkeypatch)
        sessie = await _sessie(db_session)
        debate.sound.down = True
        await debate.play(300)
        assert await debate.read() == {}

        stem.VOICES.clear()
        monkeypatch.setattr(stem, "_loaded", {})
        debate.sound.down = False
        await debate.play(480)

        where = await _where(db_session, sessie)
        assert where[Q_WANNEER] == ("speaker", "a", 60, TOEWIJZING_STEM, True)
        assert await debate.threads() == ["a@60"]
        # The first round after the restart: the voices are learned again
        # and the line is decided about at once.
        assert (await debate.read())["a@60"] == 310


ENDING = (("speaker", 1, "a"), ("interrupter", 3, "b"), ("debate_end", 4, ""))


@pytest.mark.asyncio
class TestAPartThatHasEnded:
    async def test_the_last_turn_is_read_when_the_reading_has_stopped(
        self, db_session, monkeypatch
    ):
        """The stream stops when the debate does: the reading never gets
        past the end, let alone a margin past it."""
        debate = Debate(db_session, monkeypatch, events=ENDING, audio=False)
        debate.track.stops_at = START + timedelta(seconds=240)
        await _sessie(db_session)

        await debate.play(240 + AFTER_END.total_seconds())
        assert await debate.read() == {"a@60": 240}

        await debate.play(240 + AFTER_END.total_seconds() + 10)

        assert (await debate.read())["b@180"] == 240 + AFTER_END.total_seconds() + 10
        assert await debate.threads() == ["b@180"]

    async def test_lines_that_wait_at_the_end_are_waited_for_and_then_given_up_on(
        self, db_session, monkeypatch
    ):
        debate = Debate(db_session, monkeypatch, events=ENDING)
        debate.track.stops_at = START + timedelta(seconds=240)
        debate.sound.down = True
        sessie = await _sessie(db_session)

        await debate.play(240 + AFTER_END.total_seconds() + 60)
        assert await debate.read() == {}

        await debate.play(900)

        read = await debate.read()
        given_up = ASKED_AT + RETRY_FOR.total_seconds()
        assert set(read) == {"a@60", "b@180"}
        assert all(given_up < at <= given_up + 20 for at in read.values())
        where = await _where(db_session, sessie)
        assert all(done for *_, done in where.values())


@pytest.mark.asyncio
class TestATurnThatWasRead:
    async def test_a_line_does_not_move_into_or_out_of_a_turn_that_was_read(
        self, db_session, monkeypatch
    ):
        """Read while nobody was listening, as with audio that appears
        later. The voices would put the question in a turn nobody reads
        again; it stays, and the rest still goes where it belongs."""
        debate = Debate(db_session, monkeypatch)
        sessie = await _sessie(db_session)
        debate.sound.down = True
        await debate.play(300)
        await db_session.execute(
            update(DebatSpreekbeurt)
            .where(DebatSpreekbeurt.post_id == await debate.post_of("a", 60))
            .values(beoordeeld_at=START + timedelta(seconds=300))
        )

        debate.sound.down = False
        await debate.play(600)

        where = await _where(db_session, sessie)
        assert where["r182."] == ("interrupter", "b", 180, "tijd", True)
        assert where[Q_WANNEER] == ("interrupter", "b", 180, "tijd", True)
        # Between two turns nobody had read, a line still moves.
        assert where["r230."] == ("speaker", "a", 240, TOEWIJZING_STEM, True)
        # And a line the voices leave where it is, is still theirs to say.
        assert where["r178."] == ("speaker", "a", 60, TOEWIJZING_STEM, True)
        # So the question is read where it stayed, and its thread is
        # under the message that holds it.
        assert await debate.threads() == ["b@180"]
        assert Q_WANNEER in debate.mm.messages[await debate.post_of("b", 180)]
        assert Q_WANNEER not in debate.mm.messages[await debate.post_of("a", 60)]

    async def test_the_turns_are_looked_up_only_when_a_line_is_about_to_move(
        self, db_session, monkeypatch
    ):
        debate = Debate(db_session, monkeypatch)
        await _sessie(db_session)
        asked = []
        real = svc.load_turns

        async def load_turns(*args):
            asked.append(debate.at)
            return await real(*args)

        monkeypatch.setattr(svc, "load_turns", load_turns)
        monkeypatch.setattr(DebatVraagWorker, "tick", _no_round)

        await debate.play(480)

        # Once per round in which a line moved, not once per line or round.
        assert 1 <= len(asked) == len(set(asked)) <= 4


async def _no_round(self, now=None):
    return mod.VraagTickResult()


def _events(*events: tuple[str, float, str]):
    """Events as the voices see them, and the id of each by who@seconds."""
    rows = [
        (uuid.uuid4(), kind, START + timedelta(seconds=seconds), who)
        for kind, seconds, who in events
    ]
    return as_turns(rows), {
        f"{who}@{seconds}": row_id
        for (row_id, _, _, who), (_, seconds, _) in zip(rows, events, strict=True)
    }


def _now(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


class TestRowsInPlay:
    """Which events a line that is not decided about can still change."""

    TURNS, IDS = _events(
        ("debate_start", 0, ""),
        ("speaker", 60, "a"),
        ("interrupter", 180, "b"),
        ("speaker", 240, "a"),
    )

    def _play(self, line: float, age: timedelta, under: str | None = None) -> set[str]:
        names = {row_id: name for name, row_id in self.IDS.items()}
        found = rows_in_play(
            self.TURNS, [(_now(line), self.IDS.get(under))], _now(line) + age
        )
        return {names[row_id] for row_id in found}

    def test_a_line_near_a_change_can_go_to_either_side(self):
        assert self._play(175, WAIT, "a@60") == {"a@60", "b@180"}
        assert self._play(185, WAIT, "b@180") == {"a@60", "b@180"}

    def test_a_line_far_from_any_change_stays_where_it_is(self):
        assert self._play(120, WAIT, "a@60") == set()

    def test_exactly_as_far_as_the_voices_listen(self):
        assert self._play(180 - BEFORE.total_seconds(), WAIT, "a@60") == {
            "a@60",
            "b@180",
        }
        assert self._play(180 - BEFORE.total_seconds() - 1, WAIT, "a@60") == set()
        assert self._play(180 + AFTER.total_seconds(), WAIT, "b@180") == {
            "a@60",
            "b@180",
        }
        assert self._play(180 + AFTER.total_seconds() + 1, WAIT, "b@180") == set()

    def test_it_goes_to_the_nearest_turn_of_a_person_not_the_one_next_to_it(self):
        """Just before the answer, the voice of who answers: their turn
        after the interruption is nearer than the one before."""
        assert self._play(230, WAIT, "b@180") == {"b@180", "a@240"}

    def test_where_it_is_now_can_lose_it(self):
        assert self._play(185, WAIT, "a@240") == {"a@60", "b@180", "a@240"}

    def test_a_line_without_a_turn_can_still_be_given_one(self):
        assert self._play(185, WAIT, None) == {"a@60", "b@180"}

    def test_the_start_of_the_debate_is_not_a_change_of_speaker(self):
        assert self._play(62, WAIT, "a@60") == set()

    def test_a_line_the_voices_have_not_looked_at_can_go_to_anything_near(self):
        """The events around it may not all be in: a change that is not
        known yet cannot be asked about."""
        young = WAIT - timedelta(seconds=1)

        assert self._play(120, young, "a@60") == {"a@60"}
        assert self._play(180 + REACH.total_seconds(), young, "b@180") == {
            "a@60",
            "b@180",
        }
        assert self._play(180 + REACH.total_seconds() + 1, young, "b@180") == {"b@180"}
        assert self._play(240 - REACH.total_seconds(), young, "b@180") == {
            "b@180",
            "a@240",
        }
        assert self._play(240 - REACH.total_seconds() - 1, young, "b@180") == {"b@180"}

    def test_a_line_the_voices_have_given_up_on_stays_where_it_is(self):
        assert self._play(185, NEVER_MOVES_AFTER, "b@180") == {"a@60", "b@180"}
        assert (
            self._play(185, NEVER_MOVES_AFTER + timedelta(seconds=1), "b@180") == set()
        )

    def test_the_voices_are_given_longer_than_they_take(self):
        assert NEVER_MOVES_AFTER > RETRY_FOR

    def test_no_lines_nothing_in_play(self):
        assert rows_in_play(self.TURNS, [], _now(300)) == set()


class TestMessageOf:
    def test_what_follows_a_message_is_under_it_until_the_next(self):
        turns, ids = _events(
            ("debate_start", 0, ""),
            ("speaker", 60, "a"),
            ("chairman", 100, "v"),
            ("speaker", 105, "a"),
            ("speaker", 120, "b"),
        )

        under = message_of(turns, {ids["a@60"], ids["b@120"]})

        assert under == {
            ids["a@60"]: ids["a@60"],
            ids["v@100"]: ids["a@60"],
            ids["a@105"]: ids["a@60"],
            ids["b@120"]: ids["b@120"],
        }

    def test_no_messages_nothing_under_anything(self):
        turns, _ = _events(("speaker", 60, "a"))

        assert message_of(turns, set()) == {}


class TestVoicesListen:
    def test_switched_off_they_do_not(self, monkeypatch):
        _model(monkeypatch, object())
        monkeypatch.setattr(get_settings(), "DEBAT_STEMMEN_ENABLED", False)

        assert voices_listen() is False

    def test_with_the_model_they_do(self, monkeypatch):
        _model(monkeypatch, object())

        assert voices_listen() is True

    def test_before_anybody_looked_for_the_model_it_counts_as_there(self):
        assert stem.available(get_settings().DEBAT_STEM_MODEL_PATH) is None
        assert voices_listen() is True

    def test_without_the_file_they_do_not(self, monkeypatch, tmp_path):
        path = str(tmp_path / "geen.onnx")
        monkeypatch.setattr(get_settings(), "DEBAT_STEM_MODEL_PATH", path)

        assert stem.load(path) is None

        assert stem.available(path) is False
        assert voices_listen() is False

    def test_with_too_little_memory_they_do_not(self, monkeypatch, tmp_path):
        path = tmp_path / "model.onnx"
        path.write_bytes(b"model")
        monkeypatch.setattr(get_settings(), "DEBAT_STEM_MODEL_PATH", str(path))
        monkeypatch.setattr(stem, "memory_left", lambda: stem.MEMORY_NEEDED - 1)

        assert stem.load(str(path)) is None

        assert voices_listen() is False

    def test_asking_does_not_load_the_model(self, monkeypatch):
        loaded = []
        monkeypatch.setattr(stem, "_load", loaded.append)

        voices_listen()

        assert loaded == []


class TestTheEndByTheClock:
    END = START + timedelta(minutes=4)

    def _entry(self, position: datetime | None) -> dict:
        return {
            "positie": position.isoformat() if position else None,
            "offset_ms": 2000,
        }

    def test_once_the_reading_has_stopped_nothing_more_comes(self):
        short = self._entry(self.END - timedelta(seconds=5))
        after = self.END + AFTER_END

        assert text_is_complete(short, self.END, self.END, after) is False
        assert (
            text_is_complete(short, self.END, self.END, after + timedelta(seconds=1))
            is True
        )

    def test_not_without_an_end(self):
        short = self._entry(self.END - timedelta(seconds=5))

        assert (
            text_is_complete(short, self.END, None, self.END + timedelta(hours=1))
            is False
        )

    def test_not_when_nothing_was_ever_read(self):
        late = self.END + timedelta(hours=1)

        assert text_is_complete(self._entry(None), self.END, self.END, late) is False

    def test_the_margin_reaches_every_line_the_voices_can_still_give_to_a_turn(self):
        assert MARGIN >= BEFORE
        assert MARGIN >= AFTER
        assert REACH == max(BEFORE, AFTER)

    def test_the_margin_is_all_a_turn_waits_for_when_no_line_is_open(self):
        edge = self._entry(self.END + OFFSET + MARGIN)

        assert text_is_complete(edge, self.END, None, self.END) is True


async def _line(
    db_session, sessie, row, seconds: float, *, done: bool = False, part: str = PART
) -> None:
    db_session.add(
        DebatOndertitel(
            sessie_id=sessie.id,
            debat_direct_id=part,
            start=START + timedelta(seconds=seconds),
            einde=START + timedelta(seconds=seconds + 3),
            tekst=f"r{seconds}.",
            spreekbeurt_id=row.id if row is not None else None,
            stem_klaar=done,
        )
    )
    await db_session.flush()


def _heard(read_until: float = 600, part: str = PART) -> dict:
    return {
        part: {
            "url": "https://stream.example/sub.m3u8",
            "offset_ms": 2000,
            "audio": AUDIO,
            "positie": (START + timedelta(seconds=read_until)).isoformat(),
        }
    }


@pytest.mark.asyncio
class TestWhichTurnsWait:
    """Rows written by hand: exactly which line holds which turn."""

    async def _three(self, db_session, monkeypatch, mm, **sessie):
        Outside(monkeypatch)
        _model(monkeypatch, object())
        s = await _running(db_session, **{"ondertitels": _heard(), **sessie})
        a = await _row(
            db_session, s, "speaker", 60, "a", tekst=f"{OPENING} {Q_WANNEER}"
        )
        b = await _row(
            db_session, s, "speaker", 120, "b", tekst=f"{OPENING} {Q_BUDGET}"
        )
        c = await _row(
            db_session, s, "speaker", 300, "c", tekst=f"{OPENING} {Q_BUDGET}"
        )
        await _row(db_session, s, "debate_end", 400)
        _in_channel(mm, a, b, c)
        return s, a, b, c

    async def _read(self, db_session, *rows) -> list[bool]:
        return [await _at(db_session, row) is not None for row in rows]

    async def test_a_line_at_the_edge_holds_both_turns_and_no_other(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        await _line(db_session, s, a, 118)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [False, False, True]

    async def test_once_it_is_decided_about_both_are_read(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        await _line(db_session, s, a, 118)
        await _tick(db_session, mm, FakeLLM(), 700)

        await db_session.execute(update(DebatOndertitel).values(stem_klaar=True))
        await _tick(db_session, mm, FakeLLM(), 715)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_a_line_that_is_decided_about_holds_nothing(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        await _line(db_session, s, a, 118, done=True)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_a_line_far_from_a_change_holds_nothing(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        await _line(db_session, s, b, 200)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_it_holds_until_the_voices_cannot_move_it_any_more(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        await _line(db_session, s, a, 118)
        last = 118 + NEVER_MOVES_AFTER.total_seconds()

        await _tick(db_session, mm, FakeLLM(), last)
        assert await self._read(db_session, a, b) == [False, False]

        await _tick(db_session, mm, FakeLLM(), last + 1)
        assert await self._read(db_session, a, b) == [True, True]

    async def test_a_part_without_audio_is_not_waited_for(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        quiet = _heard()
        quiet[PART]["audio"] = ""
        s, a, b, c = await self._three(db_session, monkeypatch, mm, ondertitels=quiet)
        await _line(db_session, s, a, 118)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_without_a_model_nothing_is_waited_for(self, db_session, monkeypatch):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        _model(monkeypatch, None)
        await _line(db_session, s, a, 118)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_a_line_of_another_part_holds_nothing_here(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        both = {**_heard(), **_heard(part="deel-2")}
        s, a, b, c = await self._three(
            db_session,
            monkeypatch,
            mm,
            ondertitels=both,
            debat_direct_ids=[PART, "deel-2"],
        )
        await _line(db_session, s, None, 118, part="deel-2")

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_a_line_of_a_part_nobody_listens_to_holds_nothing(
        self, db_session, monkeypatch
    ):
        """The second part has audio, this one does not: its lines are
        never decided about, and are not what the voices are asked."""
        mm = Chat()
        both = {**_heard(), **_heard(part="deel-2")}
        both[PART]["audio"] = ""
        s, a, b, c = await self._three(
            db_session,
            monkeypatch,
            mm,
            ondertitels=both,
            debat_direct_ids=[PART, "deel-2"],
        )
        await _line(db_session, s, a, 118)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b, c) == [True, True, True]

    async def test_a_line_that_was_just_said_holds_the_turn_it_is_near(
        self, db_session, monkeypatch
    ):
        """Ten seconds into the next turn, past where the voices listen
        around the change that is known. They have not looked at it yet,
        and until they do an event that is still to come can put it at a
        change."""
        mm = Chat()
        s, a, b, c = await self._three(
            db_session, monkeypatch, mm, ondertitels=_heard(330)
        )
        await _line(db_session, s, c, 310)
        young = 310 + WAIT.total_seconds() - 1

        await _tick(db_session, mm, FakeLLM(), young)
        assert await self._read(db_session, a, b) == [True, False]

        await _tick(db_session, mm, FakeLLM(), young + 1)
        assert await self._read(db_session, a, b) == [True, True]

    async def test_a_line_under_the_chairman_inside_a_turn_holds_that_turn(
        self, db_session, monkeypatch
    ):
        """The chairman says a word and the speaker carries on: one
        message. A line that goes from one to the other changes it."""
        Outside(monkeypatch)
        _model(monkeypatch, object())
        mm = Chat()
        s = await _running(db_session, ondertitels=_heard())
        a = await _row(db_session, s, "speaker", 60, "a", tekst=f"{OPENING} {Q_BUDGET}")
        v = await _row(db_session, s, "chairman", 200, "v", post=False)
        await _row(db_session, s, "speaker", 205, "a", post=False, tekst="En verder.")
        b = await _row(
            db_session, s, "speaker", 300, "b", tekst=f"{OPENING} {Q_BUDGET}"
        )
        await _row(db_session, s, "debate_end", 400)
        _in_channel(mm, a, b)
        await _line(db_session, s, v, 201)

        await _tick(db_session, mm, FakeLLM(), 700)

        assert await self._read(db_session, a, b) == [False, True]

    async def test_one_question_about_the_lines_per_debate_per_round(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        await _line(db_session, s, a, 118)
        asked = await self._count(db_session, mm)

        assert asked == 1

    async def test_and_none_at_all_when_the_voices_are_not_listened_to(
        self, db_session, monkeypatch
    ):
        mm = Chat()
        s, a, b, c = await self._three(db_session, monkeypatch, mm)
        _model(monkeypatch, None)
        await _line(db_session, s, a, 118)

        assert await self._count(db_session, mm) == 0

    async def _count(self, db_session, mm) -> int:
        statements: list[str] = []

        def seen(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        connection = (await db_session.connection()).sync_connection
        event.listen(connection, "before_cursor_execute", seen)
        try:
            await _tick(db_session, mm, FakeLLM(), 700)
        finally:
            event.remove(connection, "before_cursor_execute", seen)
        return sum("FROM debat_ondertitel" in statement for statement in statements)
