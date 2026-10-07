"""Tests for reading an answer of the bewindspersoon while it goes on.

A toezegging used to wait for the end of its turn: a minister who speaks
for ten minutes showed nothing for ten minutes. Now the part of such a turn
that is final is read as it comes. These tests are about what "final" is,
where a window of a turn that goes on ends, how far a turn was read, under
which message the reply hangs, and what the timeline and the marking do to
each other's rows when they run at the same moment.

Everything said in here is made up.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import SOORT_TOEZEGGING, DebatMarkering
from bouwmeester.models.debat_sessie import (
    DebatOndertitel,
    DebatSessie,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_stem as stem
from bouwmeester.services import debat_stemmen_service as stemmen
from bouwmeester.services import debat_vraag_service as service_mod
from bouwmeester.services import debat_vraag_worker as mod
from bouwmeester.services.debat_stemmen_service import Budget, DebatStemmen, as_turns
from bouwmeester.services.debat_tijdlijn_service import TickResult
from bouwmeester.services.debat_transcript import MESSAGE_LIMIT, split_text
from bouwmeester.services.debat_transcript_service import (
    DebatTranscript,
    derive_text,
    load_turns,
)
from bouwmeester.services.debat_vraag_service import (
    ANTWOORD_VENSTER,
    MEELEES_VENSTER,
    DebatVraagService,
    final_end,
    next_window,
    post_holding,
    running_window,
)
from bouwmeester.services.debat_vraag_worker import (
    MAX_ANSWER_WINDOWS_PER_ROUND,
    NEVER_MOVES_AFTER,
    WINDOW_ATTEMPTS,
    DebatVraagWorker,
    SubLine,
    final_lines,
    first_in_play,
    reach_of,
    rows_in_play,
    text_of,
)
from tests import test_debat_vraag_worker as w
from tests.test_debat_stemmen import AUDIO
from tests.test_debat_tijdlijn import START
from tests.test_debat_toezegging import PerKind, toegezegd, toezegging
from tests.test_debat_vraag_worker import PART

# What a bewindspersoon says. None of it has the words of a commitment,
# except the three that are toezeggingen.
INTRO = "Voorzitter, dank voor de vragen over de regeling."
T_BRIEF = "Ik zeg toe dat de Kamer voor de zomer een brief krijgt over de bezetting."
T_PROEF = "Ik stuur de Kamer in het voorjaar de evaluatie van de proef."
VERDER = "Dan is er het punt van de uitvoering in de regio."
NOG = "Daar is de afgelopen jaren veel over gezegd."
HALF = "Dat punt gaat over"
WENS = "Ik wil daar nog wel eens goed naar kijken."
Q_INTERRUPTIE = "Kan de minister toezeggen dat de Kamer daar een brief over krijgt?"


def _filler(count: int, first: int = 1) -> list[str]:
    return [
        f"Onderdeel {number} van de regeling is in de praktijk uitvoerbaar gebleken."
        for number in range(first, first + count)
    ]


@pytest.fixture(autouse=True)
def _nothing_left_over(monkeypatch):
    """What the worker remembers lives in the process; a test starts clean."""
    for memory in (mod._pause, mod._answer_pause, mod._roles):
        memory.reset()
    mod._asked_at.clear()
    stem.VOICES.clear()
    monkeypatch.setattr(stem, "_loaded", {})
    yield
    for memory in (mod._pause, mod._answer_pause, mod._roles):
        memory.reset()
    mod._asked_at.clear()
    stem.VOICES.clear()


@pytest.fixture
def handed(monkeypatch):
    """Every turn that was handed to the marking."""
    seen: list = []
    original = DebatVraagService.beoordeel_beurt

    async def record(self, beurt, context):
        seen.append(beurt)
        return await original(self, beurt, context)

    monkeypatch.setattr(DebatVraagService, "beoordeel_beurt", record)
    return seen


def _at(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def _now(seconds: float) -> datetime:
    return _at(seconds).astimezone(UTC)


# --- where the last complete sentence ends --------------------------------


class TestFinalEnd:
    def test_the_sentence_that_is_not_finished_is_left_out(self):
        tekst = f"{INTRO} {T_BRIEF} {HALF}"

        assert tekst[: final_end(tekst)] == f"{INTRO} {T_BRIEF}"

    def test_a_text_that_ends_with_a_full_stop_is_complete(self):
        tekst = f"{INTRO} {T_BRIEF}"

        assert final_end(tekst) == len(tekst)
        assert final_end(f"{tekst}  ") == len(tekst)

    def test_no_sentence_that_is_complete(self):
        assert final_end(HALF) == 0
        assert final_end("") == 0

    def test_the_dots_of_a_line_that_runs_on_end_nothing(self):
        tekst = f"{INTRO} Ik zeg toe dat de Kamer..."

        assert tekst[: final_end(tekst)] == INTRO
        assert final_end(f"{INTRO} Ik zeg toe dat de Kamer... een brief krijgt") == len(
            INTRO
        )

    def test_a_question_mark_and_an_exclamation_mark_end_a_sentence(self):
        assert final_end("Is dat zo? Zeker! En dan") == len("Is dat zo? Zeker!")


# --- which window of a turn that goes on is worth a call ------------------


class TestRunningWindow:
    def test_nothing_that_is_complete_is_nothing_to_read(self):
        assert running_window(HALF, 0) is None
        assert running_window("", 0) is None

    def test_a_toezegging_with_the_sentence_after_it_is_read_at_once(self):
        tekst = f"{INTRO} {T_BRIEF} {VERDER} {HALF}"

        vanaf, begin, einde = running_window(tekst, 0)

        assert (vanaf, begin) == (0, 0)
        # Up to the last complete sentence; the tail is for a later round.
        assert tekst[:einde] == f"{INTRO} {T_BRIEF} {VERDER}"

    def test_a_toezegging_waits_for_the_sentence_after_it(self):
        """The moment is often named in the next sentence, and a quote
        that was stored without it is not stored again with it."""
        assert running_window(f"{INTRO} {T_BRIEF}", 0) is None
        assert running_window(f"{INTRO} {T_BRIEF} {HALF}", 0) is None

    def test_one_at_the_end_is_left_for_the_next_window_whole(self):
        tekst = f"{INTRO} {T_BRIEF} {VERDER} {T_PROEF}"

        _, _, einde = running_window(tekst, 0)

        assert tekst[:einde] == f"{INTRO} {T_BRIEF} {VERDER}"
        # And once its next sentence is there, it is read from its start.
        more = f"{tekst} {NOG}"
        vanaf, begin, einde = running_window(more, einde)
        assert T_PROEF in more[vanaf:einde]
        assert more[begin:einde].endswith(f"{T_PROEF} {NOG}")

    def test_what_was_said_across_the_edge_of_what_is_final_is_seen_whole(self):
        first, second = T_BRIEF.split(" voor de zomer ")
        early = f"{INTRO} {first} voor de zomer"
        # Half a sentence: not read, however much it looks like one.
        assert running_window(early, 0) is None

        tekst = f"{early} {second} {VERDER}"
        vanaf, begin, einde = running_window(tekst, 0)

        assert T_BRIEF in tekst[begin:einde]

    def test_without_the_words_of_a_commitment_nothing_is_asked(self):
        tekst = " ".join([INTRO, *_filler(80)])

        assert len(tekst) > ANTWOORD_VENSTER
        assert running_window(tekst, 0) is None

    def test_a_wish_is_not_asked_about_until_enough_was_said(self):
        """Every other sentence of an answer has "ik wil" in it. A call for
        each would be a call a round."""
        short = " ".join([INTRO, WENS, *_filler(5)])
        assert len(short) < MEELEES_VENSTER
        assert running_window(short, 0) is None

        longer = " ".join([INTRO, WENS, *_filler(25)])
        assert MEELEES_VENSTER <= len(longer) < ANTWOORD_VENSTER
        vanaf, begin, einde = running_window(longer, 0)
        assert (vanaf, begin, einde) == (0, 0, len(longer))

    def test_the_threshold_counts_from_where_the_turn_was_read(self):
        tekst = " ".join([INTRO, *_filler(25), WENS, *_filler(5)])
        read = tekst.index(WENS)

        assert running_window(tekst, read) is None

    def test_a_full_window_is_read_as_in_a_turn_that_is_over(self):
        tekst = " ".join([INTRO, WENS, *_filler(120)])

        vanaf, begin, einde = running_window(tekst, 0)

        assert (vanaf, begin, einde) == next_window(tekst, 0)
        assert einde < len(tekst)
        assert tekst[einde - 1] == "."

    def test_a_full_window_without_the_words_is_passed_over(self):
        tekst = " ".join([INTRO, *_filler(100), T_BRIEF, VERDER])

        vanaf, begin, einde = running_window(tekst, 0)

        # Read up to where the passing over stopped, a window further.
        assert vanaf > ANTWOORD_VENSTER // 2
        assert begin < vanaf
        assert T_BRIEF in tekst[vanaf:einde]

    def test_a_window_begins_two_sentences_before_where_the_last_one_ended(self):
        tekst = f"{INTRO} {T_BRIEF} {VERDER} {NOG} {T_PROEF} {VERDER}"
        _, _, read = running_window(f"{INTRO} {T_BRIEF} {VERDER}", 0)

        vanaf, begin, einde = running_window(tekst, read)

        assert vanaf == read
        assert tekst[begin:einde].startswith(f"{T_BRIEF} {VERDER} {NOG}")

    def test_a_window_never_ends_behind_the_last_complete_sentence(self):
        sentences = [INTRO, *_filler(10), T_BRIEF, VERDER, *_filler(40), T_PROEF, NOG]
        tekst = " ".join(sentences)
        for cut in range(40, len(tekst), 37):
            found = running_window(tekst[:cut], 0)
            if found is None:
                continue
            einde = found[2]
            assert einde <= final_end(tekst[:cut])
            assert tekst[einde - 1] in ".?!"
            assert tekst[einde : einde + 1] in ("", " ")

    def test_every_toezegging_is_seen_whole_however_the_turn_comes_in(self):
        """A turn that comes in a line at a time, read as it comes and to
        its end when it is over: every sentence that commits stands whole
        in a window, with the sentence after it."""
        sentences = [INTRO, *_filler(10), T_BRIEF, VERDER, *_filler(45), T_PROEF, NOG]
        tekst = " ".join(sentences)
        for step in (23, 61, 240, 1000):
            read = 0
            windows: list[str] = []
            for cut in [*range(step, len(tekst), step), len(tekst)]:
                while (found := running_window(tekst[:cut], read)) is not None:
                    windows.append(tekst[found[1] : found[2]])
                    read = found[2]
            # The turn is over: what is left is read as it always was.
            while (found := next_window(tekst, read)) is not None:
                windows.append(tekst[found[1] : found[2]])
                read = found[2]
            assert any(f"{T_BRIEF} {VERDER}" in window for window in windows), step
            assert any(f"{T_PROEF} {NOG}" in window for window in windows), step


# --- which message of a long turn holds a quote ---------------------------


class TestPostHolding:
    TEKST = " ".join([INTRO, *_filler(30), T_BRIEF, VERDER, *_filler(30), T_PROEF, NOG])

    def test_a_turn_of_one_message(self):
        assert post_holding(self.TEKST, 2500, "eerste", ()) == "eerste"
        assert post_holding(self.TEKST, 2500, None, ("tweede",)) is None

    def test_the_message_the_quote_is_in(self):
        pieces = split_text(self.TEKST)
        assert len(pieces) == 3
        posts = ("tweede", "derde")

        assert post_holding(self.TEKST, 0, "eerste", posts) == "eerste"
        assert T_BRIEF in pieces[1]
        assert (
            post_holding(self.TEKST, self.TEKST.index(T_BRIEF), "eerste", posts)
            == "tweede"
        )
        assert T_PROEF in pieces[2]
        assert (
            post_holding(self.TEKST, self.TEKST.index(T_PROEF), "eerste", posts)
            == "derde"
        )

    def test_a_piece_without_a_message_of_its_own_is_in_the_last_one(self):
        """Someone else spoke after the turn: what still comes in goes into
        the message that is there (`fit_messages`)."""
        plek = self.TEKST.index(T_PROEF)

        assert post_holding(self.TEKST, plek, "eerste", ("tweede",)) == "tweede"

    def test_it_is_the_same_message_while_the_turn_goes_on(self):
        """A cut depends only on the text in front of it: the message of a
        quote in text that is final does not change when more is said."""
        posts = ("tweede", "derde", "vierde")
        for quote in (T_BRIEF, T_PROEF):
            plek = self.TEKST.index(quote)
            end = self.TEKST.index(" ", plek + len(quote) + 1)
            whole = post_holding(self.TEKST, plek, "eerste", posts)
            for cut in range(end, len(self.TEKST), 97):
                # Cut where a sentence ends, as a window is.
                part = self.TEKST[:cut]
                part = part[: final_end(part)]
                if len(part) < plek + len(quote):
                    continue
                assert post_holding(part, plek, "eerste", posts) == whole, cut


# --- which lines of a turn that goes on are final -------------------------


def _sub(row: uuid.UUID, seconds: float, tekst: str, klaar: bool = True) -> SubLine:
    return SubLine(uuid.uuid4(), row, _at(seconds), tekst, klaar)


class TestFinalLines:
    ROW = uuid.uuid4()

    def _lines(self) -> list[SubLine]:
        return [_sub(self.ROW, 60 + 4 * i, f"regel {i}.") for i in range(6)]

    def test_without_a_line_in_play_every_line_is_final(self):
        lines = self._lines()

        assert final_lines(lines, None) == lines

    def test_a_line_in_play_and_everything_after_it_is_left(self):
        lines = self._lines()

        assert final_lines(lines, _at(68)) == lines[:2]

    def test_a_line_in_play_before_the_turn_leaves_nothing(self):
        """A line of the turn before that the voices may still give to this
        one would land in front of everything."""
        assert final_lines(self._lines(), _at(58)) == []

    def test_what_is_final_is_how_the_text_of_the_turn_begins(self):
        lines = self._lines()
        whole = text_of(lines)

        for bound in range(60, 90, 2):
            assert whole.startswith(text_of(final_lines(lines, _at(bound))))

    def test_a_later_row_of_the_turn_is_not_read_past_a_line_in_play(self):
        other = uuid.uuid4()
        lines = [
            _sub(self.ROW, 60, "een."),
            _sub(self.ROW, 64, "twee."),
            _sub(other, 80, "drie."),
            _sub(other, 84, "vier."),
        ]

        assert text_of(final_lines(lines, _at(80))) == "een. twee."
        assert text_of(final_lines(lines, _at(84))) == "een. twee. drie."


class TestTextOf:
    def test_lines_of_a_row_with_a_space_and_row_after_row(self):
        one, two = uuid.uuid4(), uuid.uuid4()
        lines = [
            _sub(one, 60, " een "),
            _sub(one, 64, "twee"),
            _sub(two, 80, "drie "),
        ]

        assert text_of(lines) == "een  twee drie"
        assert text_of([]) == ""


class TestFirstInPlay:
    """`rows_in_play` says which events wait; this says from when."""

    EVENTS = [
        (uuid.UUID(int=1), "speaker", _at(0), "a"),
        (uuid.UUID(int=2), "interrupter", _at(100), "b"),
        (uuid.UUID(int=3), "speaker", _at(200), "m"),
    ]
    TURNS = as_turns(EVENTS)
    A, B, M = (event[0] for event in EVENTS)

    def test_the_first_line_in_play_per_event(self):
        lines = [(_at(196), self.B), (_at(204), self.M), (_at(98), self.A)]

        found = first_in_play(self.TURNS, lines, _now(260))

        assert found == {self.A: _at(98), self.B: _at(98), self.M: _at(196)}

    def test_the_same_events_as_rows_in_play(self):
        lines = [(_at(196), self.B), (_at(150), self.B), (_at(204), self.M)]
        for seconds in (210, 240, 300, 400):
            now = _now(seconds)
            assert set(first_in_play(self.TURNS, lines, now)) == rows_in_play(
                self.TURNS, lines, now
            )

    def test_a_line_that_waited_too_long_holds_nothing(self):
        late = NEVER_MOVES_AFTER.total_seconds() + 197

        assert first_in_play(self.TURNS, [(_at(196), self.B)], _now(late)) == {}
        # It can still be moved, for as long as the voices keep trying.
        assert reach_of(self.TURNS, _at(196), self.B, _now(late)) == {self.B, self.M}

    def test_a_line_far_from_a_change_reaches_nothing(self):
        assert reach_of(self.TURNS, _at(150), self.B, _now(300)) == set()


# --- the worker: an answer that goes on, rows written by hand -------------


async def _say(
    session, sessie, row, lines: list[tuple[float, str]], *, done: bool = False
) -> None:
    """Subtitle lines under a row, and the text of the row made of them."""
    for seconds, tekst in lines:
        session.add(
            DebatOndertitel(
                sessie_id=sessie.id,
                debat_direct_id=row.debat_direct_id,
                start=_at(seconds),
                einde=_at(seconds + 3),
                tekst=tekst,
                spreekbeurt_id=row.id,
                stem_klaar=done,
            )
        )
    await session.flush()
    await derive_text(session, {row.id})
    if row in session:
        await session.refresh(row)


async def _settled(session, sessie) -> dict[str, bool]:
    rows = await session.execute(
        select(DebatOndertitel.tekst, DebatOndertitel.stem_klaar).where(
            DebatOndertitel.sessie_id == sessie.id
        )
    )
    return {tekst: klaar for tekst, klaar in rows.all()}


async def _position(session, row) -> int | None:
    return await session.scalar(
        select(DebatSpreekbeurt.antwoord_gelezen_tot).where(
            DebatSpreekbeurt.id == row.id
        )
    )


async def _toezeggingen(session, sessie) -> list[tuple[str, str | None]]:
    rows = await session.execute(
        select(DebatMarkering.citaat, DebatMarkering.beurt_post_id)
        .where(
            DebatMarkering.sessie_id == sessie.id,
            DebatMarkering.soort == SOORT_TOEZEGGING,
        )
        .order_by(DebatMarkering.volgnummer)
    )
    return [tuple(row) for row in rows.all()]


def _heard(read_until: float = 600) -> dict:
    """A part the voices listen to."""
    return {
        PART: {
            "url": "https://stream.example/sub.m3u8",
            "offset_ms": 2000,
            "audio": AUDIO,
            "positie": _at(read_until).isoformat(),
        }
    }


def _listening(monkeypatch) -> None:
    """The model of the voices is there, as after its first load."""
    from bouwmeester.core.config import get_settings

    monkeypatch.setitem(stem._loaded, get_settings().DEBAT_STEM_MODEL_PATH, object())


ANSWER = [(62, INTRO), (66, T_BRIEF), (70, VERDER), (74, HALF)]
EEN_OPEN = "🤝 1 toezegging · 🔴 **open**"


async def _counts(session, mm, sessie) -> None:
    """The round of the timeline that writes what is counted under a
    message: the one writer of the message of a turn."""
    await DebatTranscript(session, mm).write_counts(TickResult(), [sessie.id])


@pytest.mark.asyncio
class TestAnAnswerThatGoesOn:
    async def _minister(self, db_session, mm, lines=ANSWER, **sessie):
        s = await w._running(db_session, **sessie)
        m = await w._row(db_session, s, "speaker", 60, "m")
        await _say(db_session, s, m, lines)
        w._in_channel(mm, m)
        return s, m

    async def test_a_toezegging_is_marked_while_the_minister_still_speaks(
        self, db_session, monkeypatch, handed
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m = await self._minister(db_session, mm)

        result = await w._tick(db_session, mm, llm, 120)

        assert result.toezeggingen == 1
        assert await _toezeggingen(db_session, s) == [(T_BRIEF, m.post_id)]
        assert [root for root, _ in mm.threads] == [m.post_id]
        # The model was shown what is complete, not the sentence that is
        # still being said.
        assert len(llm.asked) == 1
        assert f"{INTRO} {T_BRIEF} {VERDER}" in llm.asked[0]
        assert HALF not in llm.asked[0]
        assert handed[0].loopt is True

    async def test_the_turn_is_not_marked_as_read_and_how_far_it_was_read_is_kept(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        s, m = await self._minister(db_session, mm)

        result = await w._tick(db_session, mm, PerKind(), 120)

        assert await w._at(db_session, m) is None
        assert result.beoordeeld == 0
        assert await _position(db_session, m) == len(f"{INTRO} {T_BRIEF} {VERDER}")

    async def test_a_round_in_which_nothing_new_is_final_costs_nothing(
        self, db_session, monkeypatch
    ):
        outside = w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m = await self._minister(db_session, mm)
        await w._tick(db_session, mm, llm, 120)
        assert (len(llm.prompts), outside.sprekers_calls) == (1, 1)

        async def boom(cls, session, mattermost=None):
            raise AssertionError("no model is looked for when nothing is new")

        monkeypatch.setattr(DebatVraagService, "create", classmethod(boom))
        for seconds in (135, 150, 165):
            await DebatVraagWorker(db_session, mm).tick(_now(seconds))

        # No call, and nobody was asked who speaks either.
        assert (len(llm.prompts), outside.sprekers_calls) == (1, 1)

    async def test_who_speaks_is_looked_up_once_for_a_turn_that_goes_on(
        self, db_session, monkeypatch
    ):
        """Not every round: that is 240 requests an hour to Debat Direct."""
        outside = w.Outside(monkeypatch)
        mm = w.Chat()
        s, m = await self._minister(
            db_session, mm, [(62, INTRO), (66, WENS), (70, VERDER)]
        )

        for seconds in (120, 135, 150, 165):
            await w._tick(db_session, mm, PerKind(), seconds)

        assert outside.sprekers_calls == 1

    async def test_one_look_at_the_list_tells_who_everyone_is(
        self, db_session, monkeypatch
    ):
        """A member speaks and is looked up. The minister who gets the
        floor a minute later is on the same list: looking again only after
        five minutes would leave the first minutes of the answer unread."""
        outside = w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        a = await w._row(db_session, s, "speaker", 60, "a")
        await _say(db_session, s, a, ANSWER)
        w._in_channel(mm, a)

        await w._tick(db_session, mm, PerKind(), 120)

        assert outside.sprekers_calls == 1
        assert mod._roles.of(s.id, "a") is False
        assert mod._roles.of(s.id, "m") is True
        assert mod._roles.of(s.id, "gast") is None

    async def test_someone_who_is_not_on_the_list_is_asked_about_again_later(
        self, db_session, monkeypatch
    ):
        outside = w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        guest = await w._row(db_session, s, "speaker", 60, "gast")
        await _say(db_session, s, guest, ANSWER)
        w._in_channel(mm, guest)

        for seconds in (120, 135, 150):
            await w._tick(db_session, mm, PerKind(), seconds)
        assert outside.sprekers_calls == 1

        later = 120 + mod.ASK_ROLES_AGAIN.total_seconds()
        await w._tick(db_session, mm, PerKind(), later)
        assert outside.sprekers_calls == 2

    async def test_a_turn_of_a_member_that_goes_on_is_never_read(
        self, db_session, monkeypatch, handed
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        a = await w._row(db_session, s, "speaker", 60, "a")
        await _say(db_session, s, a, ANSWER)
        w._in_channel(mm, a)
        llm = PerKind()

        await w._tick(db_session, mm, llm, 120)

        assert handed == [] and llm.prompts == []
        assert await _settled(db_session, s) == dict.fromkeys(
            [text for _, text in ANSWER], False
        )

    async def test_the_lines_that_were_read_are_marked_as_decided_about(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        s, m = await self._minister(db_session, mm)

        await w._tick(db_session, mm, PerKind(), 120)

        # All of what is final, the sentence that is not finished too: it
        # is a line that was read, and it will not move.
        assert set((await _settled(db_session, s)).values()) == {True}

    async def test_what_comes_after_is_read_from_where_the_turn_was_read(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_PROEF)))
        s, m = await self._minister(db_session, mm)
        await w._tick(db_session, mm, llm, 120)

        await _say(db_session, s, m, [(78, "de uitvoering."), (82, T_PROEF), (86, NOG)])
        # Not a quarter of a minute after the last window: a turn is left
        # alone for a while after it was asked about.
        await w._tick(db_session, mm, llm, 135)
        assert len(llm.asked) == 1
        await w._tick(db_session, mm, llm, 120 + mod.RUNNING_EVERY.total_seconds())

        assert [citaat for citaat, _ in await _toezeggingen(db_session, s)] == [
            T_BRIEF,
            T_PROEF,
        ]
        second = llm.asked[1]
        # The two sentences before where the first window ended go along;
        # what was in front of them is not sent again.
        assert f"{T_BRIEF} {VERDER} {HALF} de uitvoering. {T_PROEF} {NOG}" in second
        assert INTRO not in second

    async def test_the_same_toezegging_seen_by_two_windows_is_stored_once(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        again = toegezegd(toezegging(T_BRIEF), toezegging(T_PROEF))
        llm = PerKind(toegezegd(toezegging(T_BRIEF)), again)
        s, m = await self._minister(db_session, mm)
        await w._tick(db_session, mm, llm, 120)
        await _say(db_session, s, m, [(78, "de uitvoering."), (82, T_PROEF), (86, NOG)])

        await w._tick(db_session, mm, llm, 150)

        assert [citaat for citaat, _ in await _toezeggingen(db_session, s)] == [
            T_BRIEF,
            T_PROEF,
        ]
        assert len(mm.threads) == 2

    async def test_a_full_window_does_not_wait_for_the_floor(
        self, db_session, monkeypatch
    ):
        """More than a window is waiting: the answer runs ahead of its
        reading, and holding it back would only make that worse."""
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind()
        s, m = await self._minister(db_session, mm)
        await w._tick(db_session, mm, llm, 120)
        more = ["de uitvoering.", WENS, *_filler(80)]
        await _say(
            db_session, s, m, [(78 + i / 10, text) for i, text in enumerate(more)]
        )

        await w._tick(db_session, mm, llm, 135)

        assert len(llm.asked) == 2

    async def test_a_turn_without_a_call_does_not_use_up_the_round(
        self, db_session, monkeypatch, handed
    ):
        """Two answers that are over and hold nothing to ask about come
        first. They cost no call, so the answer that goes on is still read
        in this round."""
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s = await w._running(db_session)
        stil = " ".join(_filler(3))
        m1 = await w._row(db_session, s, "speaker", 10, "m", tekst=stil)
        a = await w._row(db_session, s, "speaker", 20, "a", tekst=w.OPENING)
        m2 = await w._row(db_session, s, "speaker", 30, "m", tekst=stil)
        b = await w._row(db_session, s, "speaker", 40, "b", tekst=w.OPENING)
        m3 = await w._row(db_session, s, "speaker", 60, "m")
        await _say(db_session, s, m3, ANSWER)
        w._in_channel(mm, m1, a, m2, b, m3)

        await w._tick(db_session, mm, llm, 120)

        assert len(llm.asked) == 1
        assert [beurt.spreekbeurt_id for beurt in handed][-3:] == [m1.id, m2.id, m3.id]

    async def test_when_the_turn_is_over_the_rest_is_read_and_it_counts_as_read(
        self, db_session, monkeypatch, handed
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_PROEF)))
        s, m = await self._minister(db_session, mm)
        await w._tick(db_session, mm, llm, 120)

        # The last of the answer, with a toezegging as its very last
        # sentence: nothing follows it, and it is read all the same.
        await _say(db_session, s, m, [(78, "de uitvoering."), (82, T_PROEF)])
        a = await w._row(db_session, s, "speaker", 200, "a", tekst=w.OPENING)
        w._in_channel(mm, a)
        result = await w._tick(db_session, mm, llm, 300)

        assert await w._at(db_session, m) is not None
        assert result.toezeggingen == 1
        assert [citaat for citaat, _ in await _toezeggingen(db_session, s)] == [
            T_BRIEF,
            T_PROEF,
        ]
        last = handed[-1]
        assert last.loopt is False and last.spreekbeurt_id == m.id
        assert INTRO not in llm.asked[-1]

    async def test_a_turn_that_was_read_to_its_end_while_it_went_on_costs_no_call(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m = await self._minister(
            db_session, mm, [(62, INTRO), (66, T_BRIEF), (70, VERDER)]
        )
        await w._tick(db_session, mm, llm, 120)
        a = await w._row(db_session, s, "speaker", 200, "a", tekst=w.OPENING)
        w._in_channel(mm, a)

        await w._tick(db_session, mm, llm, 300)

        assert await w._at(db_session, m) is not None
        assert len(llm.asked) == 1
        assert len(await _toezeggingen(db_session, s)) == 1

    async def test_a_turn_half_read_before_this_was_built_goes_on_where_it_was(
        self, db_session, monkeypatch
    ):
        """How far a turn was read is still counted in characters of its
        text, so a turn that was half read when this was deployed is not
        read twice and nothing of it is skipped."""
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_PROEF)))
        lines = [(62, INTRO), (66, T_BRIEF), (70, VERDER), (74, T_PROEF), (78, NOG)]
        s, m = await self._minister(db_session, mm, lines)
        read = len(f"{INTRO} {T_BRIEF} {VERDER}")
        await db_session.execute(
            update(DebatSpreekbeurt)
            .where(DebatSpreekbeurt.id == m.id)
            .values(antwoord_gelezen_tot=read)
        )

        await w._tick(db_session, mm, llm, 120)

        assert INTRO not in llm.asked[0]
        assert llm.asked[0].count(T_PROEF) >= 1
        assert await _position(db_session, m) == len(text_of_answer(lines))

    async def test_the_members_are_read_first_and_the_cap_on_windows_holds(
        self, db_session, monkeypatch, handed
    ):
        w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        # Two answers that are over, a member, and the answer that goes on.
        kort = "Ja, dat zeg ik toe. U krijgt dat overzicht voor de zomer."
        m1 = await w._row(db_session, s, "speaker", 10, "m", tekst=kort)
        a = await w._row(
            db_session, s, "speaker", 20, "a", tekst=f"{w.OPENING} {w.Q_WANNEER}"
        )
        m2 = await w._row(db_session, s, "speaker", 30, "m", tekst=kort)
        b = await w._row(
            db_session, s, "interrupter", 40, "b", tekst=f"{w.OPENING} {w.Q_BUDGET}"
        )
        m3 = await w._row(db_session, s, "speaker", 60, "m")
        await _say(db_session, s, m3, ANSWER)
        w._in_channel(mm, m1, a, m2, b, m3)

        await w._tick(db_session, mm, PerKind(), 120)

        assert MAX_ANSWER_WINDOWS_PER_ROUND == 2
        assert [beurt.spreekbeurt_id for beurt in handed] == [a.id, b.id, m1.id, m2.id]

        handed.clear()
        await w._tick(db_session, mm, PerKind(), 135)
        assert [(beurt.spreekbeurt_id, beurt.loopt) for beurt in handed] == [
            (m3.id, True)
        ]

    async def test_a_window_that_fails_leaves_the_turn_alone_and_not_the_debate(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = PerKind(RuntimeError("weg"), toegezegd(toezegging(T_BRIEF)))
        s, m = await self._minister(db_session, mm)

        result = await w._tick(db_session, mm, llm, 120)

        assert result.fouten == 1
        assert await _position(db_session, m) is None
        assert mod._answer_pause.waiting(m.id, _now(121))
        assert not mod._pause.waiting(s.id, _now(121))
        # Left alone for a while, then asked again and read.
        await w._tick(db_session, mm, llm, 135)
        assert len(llm.asked) == 1
        await w._tick(db_session, mm, llm, 120 + mod.PAUSE_FIRST.total_seconds())
        assert len(await _toezeggingen(db_session, s)) == 1

    async def test_a_window_that_keeps_failing_is_passed_over_not_the_turn(
        self, db_session, monkeypatch
    ):
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = PerKind(*[RuntimeError("weg")] * WINDOW_ATTEMPTS)
        s, m = await self._minister(db_session, mm)

        seconds = 120.0
        for _ in range(WINDOW_ATTEMPTS):
            await w._tick(db_session, mm, llm, seconds)
            seconds += mod.PAUSE_MAX.total_seconds() + 1

        assert len(llm.asked) == WINDOW_ATTEMPTS
        assert await _position(db_session, m) == len(f"{INTRO} {T_BRIEF} {VERDER}")
        assert await w._at(db_session, m) is None

    async def test_the_place_is_kept_with_what_was_found_in_one_commit(
        self, db_session, monkeypatch
    ):
        """Kept apart, a restart between the two would leave a toezegging
        stored for a turn that says nothing of it was read; when that turn
        is over and short, it would count as read without its rest."""
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m = await self._minister(db_session, mm)

        async def lost(self, row_id, position):
            raise AssertionError("the worker died here")

        monkeypatch.setattr(DebatVraagWorker, "_keep_position", lost)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        await w._tick(db_session, mm, llm, 120)

        assert len(await _toezeggingen(db_session, s)) == 1
        assert await _position(db_session, m) == len(f"{INTRO} {T_BRIEF} {VERDER}")


def text_of_answer(lines: list[tuple[float, str]]) -> str:
    return " ".join(text for _, text in lines)


@pytest.mark.asyncio
class TestTheLinesOfATurn:
    async def test_the_text_made_of_the_lines_is_the_text_of_the_turn(self, db_session):
        """How far a turn was read counts in the text made of its lines
        while it goes on, and in the text of its rows when it is over.
        Those have to be the same text."""
        s = await w._running(db_session)
        m = await w._row(db_session, s, "speaker", 60, "m")
        await w._row(
            db_session, s, "chairman", 80, "v", post=False, tekst="Gaat u door."
        )
        more = await w._row(db_session, s, "speaker", 84, "m", post=False)
        await _say(db_session, s, m, [(62, f" {INTRO} "), (66, T_BRIEF)])
        await _say(db_session, s, more, [(86, VERDER), (90, f"{HALF} ")])

        turn = (await load_turns(db_session, s.id, PART))[0]
        lines = await DebatVraagWorker(db_session, w.Chat())._turn_lines(turn)

        assert [line.tekst.strip() for line in lines] == [INTRO, T_BRIEF, VERDER, HALF]
        assert text_of(lines) == turn.text
        for count in range(len(lines) + 1):
            assert turn.text.startswith(text_of(lines[:count]))


@pytest.mark.asyncio
class TestWhatTheVoicesCanStillMove:
    """With the voices listening: a line they have not decided about."""

    async def _debate(self, db_session, monkeypatch, mm):
        w.Outside(monkeypatch)
        _listening(monkeypatch)
        s = await w._running(db_session, ondertitels=_heard())
        b = await w._row(
            db_session, s, "interrupter", 40, "b", tekst=f"{w.OPENING} {Q_INTERRUPTIE}"
        )
        m = await w._row(db_session, s, "speaker", 60, "m")
        w._in_channel(mm, b, m)
        return s, b, m

    async def test_a_line_in_play_and_what_was_said_after_it_is_not_read_yet(
        self, db_session, monkeypatch
    ):
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_PROEF)))
        s, b, m = await self._debate(db_session, monkeypatch, mm)
        await _say(
            db_session, s, m, [(80, INTRO), (84, T_BRIEF), (88, VERDER)], done=True
        )
        # Said twenty seconds ago: the voices have not looked yet.
        await _say(db_session, s, m, [(280, NOG)])
        await _say(db_session, s, m, [(284, T_PROEF), (288, VERDER)], done=True)

        await w._tick(db_session, mm, llm, 300)

        assert len(llm.asked) == 1
        assert T_BRIEF in llm.asked[0] and T_PROEF not in llm.asked[0]
        assert await _position(db_session, m) == len(f"{INTRO} {T_BRIEF} {VERDER}")
        assert (await _settled(db_session, s))[NOG] is False

        # Half a minute later the voices have left it where it is.
        await db_session.execute(
            update(DebatOndertitel)
            .where(DebatOndertitel.tekst == NOG)
            .values(stem_klaar=True)
        )
        await w._tick(db_session, mm, llm, 330)

        assert len(llm.asked) == 2 and T_PROEF in llm.asked[1]

    async def test_the_start_of_an_answer_waits_for_the_change_of_speaker(
        self, db_session, monkeypatch
    ):
        """A sentence at the end of the interruption that the voices may
        still give to the bewindspersoon would land in front of all the
        rest. A toezegging of a member's words must not hang there."""
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, b, m = await self._debate(db_session, monkeypatch, mm)
        await _say(db_session, s, b, [(58, "Dat wil ik graag weten.")])
        await _say(
            db_session, s, m, [(80, INTRO), (84, T_BRIEF), (88, VERDER)], done=True
        )

        await w._tick(db_session, mm, llm, 150)

        assert llm.asked == []
        assert await w._at(db_session, b) is None

    async def test_of_two_lines_in_play_the_first_one_counts(
        self, db_session, monkeypatch
    ):
        """One at the start of the answer and one that was only just said,
        under a word of the chairman inside the turn. What stands between
        them is not final: the first can still land in front of it."""
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, b, m = await self._debate(db_session, monkeypatch, mm)
        # The interruption was read already; the answer waits for nothing
        # but its own lines.
        await db_session.execute(
            update(DebatSpreekbeurt)
            .where(DebatSpreekbeurt.id == b.id)
            .values(beoordeeld_at=_now(100))
        )
        await _say(db_session, s, b, [(58, "Dat wil ik graag weten.")])
        await _say(
            db_session, s, m, [(80, INTRO), (84, T_BRIEF), (88, VERDER)], done=True
        )
        word = await w._row(db_session, s, "chairman", 100, "v", post=False)
        await _say(db_session, s, word, [(140, NOG)])

        await w._tick(db_session, mm, llm, 150)

        assert llm.asked == []

    async def test_a_line_that_waited_too_long_is_read_and_stays_where_it_is(
        self, db_session, monkeypatch
    ):
        """After `NEVER_MOVES_AFTER` a turn is read as it is. The voices
        keep trying for ten minutes, so the line is marked as decided:
        what was read does not change under its thread."""
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, b, m = await self._debate(db_session, monkeypatch, mm)
        await _say(db_session, s, b, [(58, "Dat wil ik graag weten.")])
        await _say(
            db_session, s, m, [(80, INTRO), (84, T_BRIEF), (88, VERDER)], done=True
        )

        late = 58 + NEVER_MOVES_AFTER.total_seconds() + 1
        await w._tick(db_session, mm, llm, late)
        # The interruption was read in that round, and the answer after it.
        await w._tick(db_session, mm, llm, late + 15)

        assert len(await _toezeggingen(db_session, s)) == 1
        assert (await _settled(db_session, s))["Dat wil ik graag weten."] is True
        under = await db_session.scalar(
            select(DebatOndertitel.spreekbeurt_id).where(
                DebatOndertitel.tekst == "Dat wil ik graag weten."
            )
        )
        assert under == b.id

    async def test_an_answer_waits_for_the_interruption_before_it_to_be_read(
        self, db_session, monkeypatch, handed
    ):
        """A toezegging at the start of an answer is tied to the question
        that was marked in the interruption before it."""
        mm = w.Chat()
        s = await w._running(db_session, ondertitels=_heard())
        outside = w.Outside(monkeypatch)
        _listening(monkeypatch)
        a = await w._row(db_session, s, "speaker", 0, "a", tekst=w.OPENING)
        b = await w._row(
            db_session, s, "interrupter", 40, "b", tekst=f"{w.OPENING} {Q_INTERRUPTIE}"
        )
        m = await w._row(db_session, s, "speaker", 60, "m")
        w._in_channel(mm, a, b, m)
        # Undecided at the change from a to b: both wait, the answer does
        # not wait for the voices itself.
        await _say(db_session, s, a, [(38, "Tot zover.")])
        await _say(
            db_session, s, m, [(80, INTRO), (84, T_BRIEF), (88, VERDER)], done=True
        )

        await w._tick(db_session, mm, PerKind(), 120)
        assert handed == []
        # And nobody was asked who speaks: there is nothing to read yet.
        assert outside.sprekers_calls == 0

        await db_session.execute(
            update(DebatOndertitel)
            .where(DebatOndertitel.tekst == "Tot zover.")
            .values(stem_klaar=True)
        )
        await w._tick(db_session, mm, PerKind(), 135)

        assert [beurt.spreekbeurt_id for beurt in handed] == [a.id, b.id, m.id]
        answer = handed[-1]
        assert answer.loopt is True
        assert answer.voorafgaand == "Kamerlid B (Y)"
        assert Q_INTERRUPTIE in answer.voorafgaand_tekst


@pytest.mark.asyncio
class TestHowLongAnAnswerWaitsForTheTurnBefore:
    async def _debate(self, db_session, monkeypatch, mm, kind: str):
        w.Outside(monkeypatch)
        _listening(monkeypatch)
        s = await w._running(db_session, ondertitels=_heard())
        a = await w._row(db_session, s, "speaker", 0, "a", tekst=w.OPENING)
        b = await w._row(
            db_session, s, kind, 40, "b", tekst=f"{w.OPENING} {Q_INTERRUPTIE}"
        )
        m = await w._row(db_session, s, "speaker", 60, "m")
        w._in_channel(mm, a, b, m)
        # Undecided at the change from a to b: b is not read yet.
        await _say(db_session, s, a, [(38, "Tot zover.")])
        await _say(
            db_session, s, m, [(80, INTRO), (84, T_BRIEF), (88, VERDER)], done=True
        )
        return s, b, m

    async def test_not_for_a_turn_that_is_no_interruption(
        self, db_session, monkeypatch, handed
    ):
        """The turn before is a term of a member. A toezegging is tied to
        nothing in it, so the answer does not wait behind its lines."""
        mm = w.Chat()
        s, b, m = await self._debate(db_session, monkeypatch, mm, "speaker")

        await w._tick(db_session, mm, PerKind(), 125)

        assert [beurt.spreekbeurt_id for beurt in handed] == [m.id]
        assert await w._at(db_session, b) is None

    async def test_and_for_an_interruption_not_for_ever(
        self, db_session, monkeypatch, handed
    ):
        mm = w.Chat()
        s, b, m = await self._debate(db_session, monkeypatch, mm, "interrupter")
        bound = 60 + mod.WAIT_FOR_INTERRUPTION.total_seconds()

        await w._tick(db_session, mm, PerKind(), bound - 1)
        assert handed == []

        await w._tick(db_session, mm, PerKind(), bound)
        assert [beurt.spreekbeurt_id for beurt in handed] == [m.id]
        assert await w._at(db_session, b) is None


@pytest.mark.asyncio
class TestWhatARoundDidNotGetTo:
    async def test_an_answer_is_not_read_in_a_round_that_did_not_reach_the_turn_before(
        self, db_session, monkeypatch, handed
    ):
        """More turns of members wait than a round reads. The interruption
        before the answer is one of them and is not reached: the answer
        waits another round, whatever the round set out to do."""
        w.Outside(monkeypatch)
        monkeypatch.setattr(mod, "MAX_TURNS", 1)
        mm = w.Chat()
        s = await w._running(db_session)
        a = await w._row(
            db_session, s, "speaker", 0, "a", tekst=f"{w.OPENING} {w.Q_WANNEER}"
        )
        b = await w._row(
            db_session, s, "interrupter", 40, "b", tekst=f"{w.OPENING} {Q_INTERRUPTIE}"
        )
        m = await w._row(db_session, s, "speaker", 60, "m")
        await _say(db_session, s, m, ANSWER)
        w._in_channel(mm, a, b, m)

        await w._tick(db_session, mm, PerKind(), 120)
        assert [beurt.spreekbeurt_id for beurt in handed] == [a.id]

        await w._tick(db_session, mm, PerKind(), 135)
        assert [beurt.spreekbeurt_id for beurt in handed] == [a.id, b.id, m.id]

    async def test_a_window_another_worker_stored_is_not_taken_for_the_whole_turn(
        self, db_session, monkeypatch
    ):
        """During a deploy two workers read the same first window. The
        second finds what the first stored. For a turn that is over and
        short that means it was read; for one that goes on it means this
        window was, and no more than that."""
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s = await w._running(db_session)
        m = await w._row(db_session, s, "speaker", 60, "m")
        await _say(db_session, s, m, ANSWER)
        w._in_channel(mm, m)
        db_session.add(
            DebatMarkering(
                sessie_id=s.id,
                spreekbeurt_id=m.id,
                beurt_sleutel=service_mod.turn_sleutel(m.id),
                volgnummer=1,
                soort=SOORT_TOEZEGGING,
                status="open",
                channel_id=s.channel_id,
                beurt_post_id=m.post_id,
                thread_post_id="reply000000000000000000001",
                spreker="Bewindspersoon A (Minister van Voorbeelden)",
                gericht_aan="",
                citaat=T_BRIEF,
                samenvatting="",
                moment=m.event_start,
            )
        )
        await db_session.flush()

        await w._tick(db_session, mm, llm, 120)

        assert len(await _toezeggingen(db_session, s)) == 1
        # Read as far as the window, not to the end of what is there.
        assert await _position(db_session, m) == len(f"{INTRO} {T_BRIEF} {VERDER}")


# --- under which message the reply hangs ----------------------------------


@pytest.mark.asyncio
class TestTheMessageOfAToezegging:
    LONG = [INTRO, *_filler(30), T_BRIEF, VERDER]

    async def _long(self, db_session, monkeypatch, mm):
        w.Outside(monkeypatch)
        s = await w._running(db_session)
        m = await w._row(db_session, s, "speaker", 60, "m")
        await _say(
            db_session, s, m, [(62 + 4 * i, text) for i, text in enumerate(self.LONG)]
        )
        mm.messages[m.post_id] = w.KOP
        await w._transcribe(db_session, mm, s)
        turn = (await load_turns(db_session, s.id, PART))[0]
        assert len(turn.vervolg) == 1
        return s, m, turn.vervolg[0]

    async def test_the_reply_hangs_under_the_message_that_holds_the_quote(
        self, db_session, monkeypatch
    ):
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m, second = await self._long(db_session, monkeypatch, mm)
        assert T_BRIEF in mm.messages[second]
        assert len(" ".join(self.LONG)) > MESSAGE_LIMIT

        await w._tick(db_session, mm, llm, 400)

        assert await _toezeggingen(db_session, s) == [(T_BRIEF, second)]
        assert [root for root, _ in mm.threads] == [second]
        # And that message counts it, not the first, once the timeline
        # has written it.
        assert "---" not in mm.messages[second]
        await _counts(db_session, mm, s)
        assert mm.messages[second].endswith(f"\n\n---\n{EEN_OPEN}")
        assert "---" not in mm.messages[m.post_id]

    async def test_the_text_that_grows_keeps_the_count_under_that_message(
        self, db_session, monkeypatch
    ):
        """The transcription writes the last message of a turn again with
        every line that comes in. It is the one that puts a message
        together, so the count has to come back through it."""
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m, second = await self._long(db_session, monkeypatch, mm)
        await w._tick(db_session, mm, llm, 400)
        await _counts(db_session, mm, s)

        await _say(db_session, s, m, [(300, NOG)])
        await w._transcribe(db_session, mm, s)

        assert mm.messages[second].endswith(f"{NOG}\n\n---\n{EEN_OPEN}")
        assert "---" not in mm.messages[m.post_id]

    async def test_a_change_of_its_status_is_written_under_that_message(
        self, db_session, monkeypatch
    ):
        """The round of the reactions writes the count again from the row."""
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        s, m, second = await self._long(db_session, monkeypatch, mm)
        await w._tick(db_session, mm, llm, 400)
        await _counts(db_session, mm, s)
        before = mm.messages[m.post_id]
        updates = len(mm.updates)

        # As the round of the reactions leaves it: the row changed, and
        # the count under its message is out of date.
        await db_session.execute(
            update(DebatMarkering)
            .where(DebatMarkering.sessie_id == s.id)
            .values(status="beantwoord", statusregel_at=None)
        )
        assert await service_mod.schrijf_statusregel(db_session, mm, second) is None
        assert len(mm.updates) == updates
        await _counts(db_session, mm, s)

        assert mm.messages[second].endswith("\n\n---\n🤝 1 toezegging · nagekomen")
        assert mm.messages[m.post_id] == before
        # One message was written: the one that counts it.
        assert [post_id for post_id, _ in mm.updates[updates:]] == [second]

    async def test_a_question_of_a_member_still_hangs_under_the_first_message(
        self, db_session, monkeypatch
    ):
        from tests.test_debat_vragen import antwoord, vraag

        w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        tekst = " ".join([w.OPENING, *_filler(30), w.Q_WANNEER])
        a = await w._row(db_session, s, "speaker", 60, "a", tekst=tekst)
        mm.messages[a.post_id] = w.KOP
        await w._transcribe(db_session, mm, s)
        turn = (await load_turns(db_session, s.id, PART))[0]
        assert len(turn.vervolg) == 1 and w.Q_WANNEER in mm.messages[turn.vervolg[0]]
        await w._row(db_session, s, "debate_end", 300)

        await w._tick(db_session, mm, w.FakeLLM(antwoord(vraag(w.Q_WANNEER))), 700)

        assert [root for root, _ in mm.threads] == [a.post_id]


# --- two real sessions: the timeline and the marking at the same moment ---


@pytest.fixture
async def real(_test_engine):
    """Sessions that really commit, and debates that are cleaned up after.

    `db_session` is one connection in one transaction: a row it locks is
    never locked for itself, and it cannot show what another session sees.
    """
    sessions: list[AsyncSession] = []
    sessie_ids: list[uuid.UUID] = []

    def new_session() -> AsyncSession:
        session = AsyncSession(bind=_test_engine, expire_on_commit=False)
        sessions.append(session)
        return session

    def remember(sessie_id: uuid.UUID) -> None:
        sessie_ids.append(sessie_id)

    try:
        yield new_session, remember
    finally:
        for session in sessions:
            await session.rollback()
            await session.close()
        cleanup = AsyncSession(bind=_test_engine)
        await cleanup.execute(delete(DebatSessie).where(DebatSessie.id.in_(sessie_ids)))
        await cleanup.commit()
        await cleanup.close()


@pytest.mark.asyncio
class TestTheVoicesAndTheMarkingAtTheSameMoment:
    """The timeline moves lines between turns while the marking reads one.

    What was read must not change under its thread. That rests on one
    thing: the voices move a line only while it is not marked as decided,
    and the marking marks what it reads before it reads it. Both are
    statements on the same rows, so they are tested on two connections.
    """

    async def _debate(self, real):
        new_session, remember = real
        setup = new_session()
        s = await w._running(setup, ondertitels=_heard())
        remember(s.id)
        b = await w._row(setup, s, "interrupter", 40, "b", tekst=w.OPENING)
        m = await w._row(setup, s, "speaker", 60, "m")
        await _say(setup, s, m, [(62, INTRO), (66, T_BRIEF), (70, VERDER)])
        await setup.commit()
        return s, b, m

    async def _final(self, session, s, m, seconds: float = 400):
        worker = DebatVraagWorker(session, w.Chat())
        await worker._waiting(s.id, _now(seconds))
        item = next(i for i in worker._going[s.id] if i.turn.row_id == m.id)
        return worker, await worker._final(s.id, item, _now(seconds))

    async def _voice_line(self, session, tekst: str) -> stemmen.Line:
        row = (
            await session.execute(
                select(
                    DebatOndertitel.id,
                    DebatOndertitel.start,
                    DebatOndertitel.einde,
                    DebatOndertitel.spreekbeurt_id,
                    DebatOndertitel.stem_klaar,
                ).where(DebatOndertitel.tekst == tekst)
            )
        ).one()
        return stemmen.Line(*row)

    async def _text(self, session, row) -> str:
        return (
            await session.scalar(
                select(DebatSpreekbeurt.tekst).where(DebatSpreekbeurt.id == row.id)
            )
            or ""
        )

    async def test_a_line_that_was_read_is_not_moved_afterwards(
        self, real, monkeypatch
    ):
        _listening(monkeypatch)
        new_session, _ = real
        s, b, m = await self._debate(real)
        marking, timeline = new_session(), new_session()
        # The voices looked at the line before the marking read the turn.
        line = await self._voice_line(timeline, T_BRIEF)
        await timeline.commit()

        worker, final = await self._final(marking, s, m)
        assert final is not None and await worker._settle(final) is True

        voices = DebatStemmen(timeline, None, Budget.share(1))
        moved = await voices._assign(line, b.id)
        await timeline.commit()

        assert moved is False
        check = new_session()
        assert await self._text(check, m) == f"{INTRO} {T_BRIEF} {VERDER}"
        assert T_BRIEF not in await self._text(check, b)

    async def test_a_line_the_voices_are_moving_is_not_waited_for(
        self, real, monkeypatch
    ):
        """The voices have moved a line and not committed yet: they hold
        it. Waiting for it while they wait for a line held here would be a
        deadlock, so the marking passes it over, sees that not every line
        has its mark, and leaves the turn for the next round."""
        _listening(monkeypatch)
        new_session, _ = real
        s, b, m = await self._debate(real)
        marking, timeline = new_session(), new_session()
        worker, final = await self._final(marking, s, m)
        assert final is not None
        assert [line.tekst for line in final.lines] == [INTRO, T_BRIEF, VERDER]
        await marking.commit()

        line = await self._voice_line(timeline, T_BRIEF)
        voices = DebatStemmen(timeline, None, Budget.share(1))
        assert await voices._assign(line, b.id) is True

        # At once, while the voices still hold the line.
        assert await asyncio.wait_for(worker._settle(final), 2) is False
        await marking.commit()
        # And the lines that were free have their mark, in their order.
        assert await _settled(new_session(), s) == {
            INTRO: True,
            T_BRIEF: False,
            VERDER: True,
        }

        await timeline.commit()
        # The next round reads the turn as it is now.
        worker, final = await self._final(marking, s, m)
        assert [line.tekst for line in final.lines] == [INTRO, VERDER]
        assert await worker._settle(final) is True

    async def test_a_line_the_voices_hold_and_leave_where_it_is(
        self, real, monkeypatch
    ):
        """Held and not moved: the turn still begins with the same lines,
        and one of them has no mark. It is not read until it has."""
        _listening(monkeypatch)
        new_session, _ = real
        s, b, m = await self._debate(real)
        marking, timeline = new_session(), new_session()
        worker, final = await self._final(marking, s, m)
        await marking.commit()

        await timeline.execute(
            select(DebatOndertitel.id)
            .where(DebatOndertitel.tekst == T_BRIEF)
            .with_for_update()
        )
        assert await asyncio.wait_for(worker._settle(final), 2) is False
        await marking.commit()

        await timeline.rollback()
        worker, final = await self._final(marking, s, m)
        assert await worker._settle(final) is True

    async def test_a_line_that_comes_in_meanwhile_lands_behind_what_is_read(
        self, real, monkeypatch
    ):
        """The transcription adds lines while the marking reads. A new
        line is later than every line that is there."""
        new_session, _ = real
        s, b, m = await self._debate(real)
        marking, timeline = new_session(), new_session()
        worker, final = await self._final(marking, s, m)
        await marking.commit()

        await _say(timeline, s, m, [(74, NOG)])
        await timeline.commit()

        assert await worker._settle(final) is True
        assert (await self._text(new_session(), m)).startswith(final.tekst)

    async def test_two_markings_at_once_store_a_window_once(self, real, monkeypatch):
        """Two workers during a deploy read the same window."""
        w.Outside(monkeypatch)
        new_session, _ = real
        s, b, m = await self._debate(real)
        mm = w.Chat()
        mm.messages[m.post_id] = w.KOP
        mm.messages[b.post_id] = w.KOP

        async def tick(session):
            llm = PerKind(toegezegd(toezegging(T_BRIEF)))
            return await DebatVraagWorker(session, mm, llm).tick(_now(400))

        one, two = new_session(), new_session()
        # The interruption first, then the answer that goes on.
        await tick(one)
        await asyncio.gather(tick(one), tick(two))

        check = new_session()
        assert len(await _toezeggingen(check, s)) == 1
        assert len(mm.threads) == 1


class Channel(w.Chat):
    """Also remembers who wrote which message, in the order it happened."""

    def __init__(self) -> None:
        super().__init__()
        self.who = ""
        self.written: list[tuple[str, str, str]] = []

    async def update_post(self, post_id, message, props=None):
        self.written.append((self.who, post_id, message))
        return await super().update_post(post_id, message, props)


@pytest.mark.asyncio
class TestOneWriterOfAMessage:
    """The message of a turn that goes on is written by the transcription,
    line after line. The marking used to read it, put the count under it
    and write it back; whatever the transcription wrote in between was
    gone from the channel. Now the marking writes no message of a turn at
    all. Two connections, as the two loops of the worker have them."""

    async def _debate(self, real, mm):
        new_session, remember = real
        setup = new_session()
        s = await w._running(setup)
        remember(s.id)
        m = await w._row(setup, s, "speaker", 60, "m")
        await _say(setup, s, m, [(62, INTRO), (66, T_BRIEF), (70, VERDER)])
        mm.messages[m.post_id] = w.KOP
        await setup.commit()
        return s, m

    async def _timeline(self, session, mm, s, counts: bool = True) -> None:
        mm.who = "tijdlijn"
        await w._transcribe(session, mm, s)
        if counts:
            await _counts(session, mm, s)
        await session.commit()

    async def _marking(self, session, mm, llm, seconds: float) -> None:
        mm.who = "markering"
        await DebatVraagWorker(session, mm, llm).tick(_now(seconds))
        await session.commit()

    async def test_the_marking_writes_no_message_of_a_turn(self, real, monkeypatch):
        w.Outside(monkeypatch)
        new_session, _ = real
        mm = Channel()
        s, m = await self._debate(real, mm)
        timeline, marking = new_session(), new_session()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        await self._timeline(timeline, mm, s)

        # The marking finds a toezegging and posts its reply; meanwhile
        # the answer goes on and the transcription writes the next line.
        await self._marking(marking, mm, llm, 120)
        assert len(mm.threads) == 1
        await _say(timeline, s, m, [(74, NOG)])
        await timeline.commit()
        await self._timeline(timeline, mm, s, counts=False)
        # The round of the reactions comes by with what it read earlier.
        mm.who = "markering"
        assert await service_mod.schrijf_statusregel(marking, mm, m.post_id) is None
        await marking.commit()
        await self._timeline(timeline, mm, s)

        assert {who for who, post_id, _ in mm.written if post_id == m.post_id} == {
            "tijdlijn"
        }
        assert mm.messages[m.post_id] == (
            f"{w.KOP}\n{INTRO} {T_BRIEF} {VERDER} {NOG}\n\n---\n{EEN_OPEN}"
        )
        # No message that was written ever said less than the one before.
        bodies = [
            text.split("\n\n---")[0] for _, p, text in mm.written if p == m.post_id
        ]
        assert all(b.startswith(a) for a, b in zip(bodies, bodies[1:], strict=False))

    async def test_both_at_the_same_moment_lose_no_line_and_no_count(
        self, real, monkeypatch
    ):
        w.Outside(monkeypatch)
        new_session, _ = real
        mm = Channel()
        s, m = await self._debate(real, mm)
        timeline, marking = new_session(), new_session()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)))
        await self._timeline(timeline, mm, s)
        await _say(timeline, s, m, [(74, NOG)])
        await timeline.commit()

        async def mark() -> None:
            await DebatVraagWorker(marking, mm, llm).tick(_now(120))
            await marking.commit()

        async def write() -> None:
            await w._transcribe(timeline, mm, s)
            await _counts(timeline, mm, s)
            await timeline.commit()

        await asyncio.gather(mark(), write())
        # Whatever the order was, the next round of the timeline has it.
        await write()

        assert mm.messages[m.post_id] == (
            f"{w.KOP}\n{INTRO} {T_BRIEF} {VERDER} {NOG}\n\n---\n{EEN_OPEN}"
        )
        stale = await new_session().scalar(
            select(DebatMarkering.statusregel_at).where(
                DebatMarkering.sessie_id == s.id
            )
        )
        assert stale is not None

    async def test_a_count_that_changes_while_its_message_is_written_is_not_lost(
        self, real, monkeypatch
    ):
        """Which rows were out of date is read before the message is
        written. A reaction that lands during the write leaves its row out
        of date, and the next round writes it."""
        w.Outside(monkeypatch)
        new_session, _ = real
        mm = Channel()
        s, m = await self._debate(real, mm)
        timeline, marking = new_session(), new_session()
        await self._timeline(timeline, mm, s)
        await self._marking(marking, mm, PerKind(toegezegd(toezegging(T_BRIEF))), 120)
        await self._timeline(timeline, mm, s)
        assert mm.messages[m.post_id].endswith(EEN_OPEN)

        async def react(*args, **kwargs):
            # Lands between the count being read and the row being marked.
            await marking.execute(
                update(DebatMarkering)
                .where(DebatMarkering.sessie_id == s.id)
                .values(status="beantwoord", statusregel_at=None)
            )
            await marking.commit()
            return True

        await marking.execute(
            update(DebatMarkering)
            .where(DebatMarkering.sessie_id == s.id)
            .values(statusregel_at=None)
        )
        await marking.commit()
        with monkeypatch.context() as during:
            during.setattr(mm, "update_post", react)
            await _counts(timeline, mm, s)
        await timeline.commit()
        await self._timeline(timeline, mm, s)

        assert mm.messages[m.post_id].endswith("🤝 1 toezegging · nagekomen")

    async def test_a_debate_that_is_over_still_gets_its_counts(
        self, db_session, monkeypatch
    ):
        """People tick questions off after the debate. The timeline no
        longer follows it, and its round still writes what changed."""
        from bouwmeester.models.debat_sessie import TIJDLIJN_AFGELOPEN
        from bouwmeester.services.debat_tijdlijn_service import DebatTijdlijnService

        mm = w.Chat()
        s = await w._running(db_session, tijdlijn_status=TIJDLIJN_AFGELOPEN)
        a = await w._row(db_session, s, "speaker", 60, "a", tekst=w.OPENING)
        mm.messages[a.post_id] = w.KOP
        await w._marked(db_session, s, a)

        await DebatTijdlijnService(db_session, mm).tick(_now(90000))

        assert mm.messages[a.post_id] == f"{w.KOP}\n{w.OPENING}\n\n---\n{w.STATUS_EEN}"

    async def test_a_message_that_cannot_be_written_is_given_up_when_nobody_follows(
        self, db_session, monkeypatch
    ):
        from bouwmeester.models.debat_sessie import TIJDLIJN_AFGELOPEN

        mm = w.Chat()
        s = await w._running(db_session, tijdlijn_status=TIJDLIJN_AFGELOPEN)
        a = await w._row(db_session, s, "speaker", 60, "a", tekst=w.OPENING)
        mm.messages[a.post_id] = w.KOP
        await w._marked(db_session, s, a)

        async def refused(post_id, message, props=None):
            return False

        monkeypatch.setattr(mm, "update_post", refused)
        # Followed: tried again next round. Not followed: once.
        await DebatTranscript(db_session, mm).write_counts(TickResult(), [s.id])
        assert await self._stale(db_session, s) == 1
        await DebatTranscript(db_session, mm).write_counts(TickResult(), [])
        assert await self._stale(db_session, s) == 0

    async def _stale(self, session, s) -> int:
        rows = await session.execute(
            select(DebatMarkering.id).where(
                DebatMarkering.sessie_id == s.id,
                DebatMarkering.statusregel_at.is_(None),
            )
        )
        return len(rows.all())


@pytest.mark.asyncio
class TestWhatTheVoicesKeepForALine:
    async def test_what_was_kept_for_a_line_the_marking_marked_is_let_go(
        self, db_session
    ):
        """The voices keep what a line sounds like until they decide about
        it. A line the marking marked as decided is never decided about by
        them, so nothing would ever let it go."""
        s = await w._running(db_session, ondertitels=_heard())
        m = await w._row(db_session, s, "speaker", 60, "m")
        await _say(db_session, s, m, [(62, INTRO)], done=True)
        await _say(db_session, s, m, [(66, T_BRIEF)])
        ids = dict(
            (
                await db_session.execute(
                    select(DebatOndertitel.tekst, DebatOndertitel.id).where(
                        DebatOndertitel.sessie_id == s.id
                    )
                )
            ).all()
        )
        # Long after: nothing was said lately, so nothing is listened to.
        now = _now(62 + stemmen.RETRY_FOR.total_seconds() - 1 + 600)
        held = stem.VOICES.of(s.id, now)
        held.lines[ids[INTRO]] = object()
        held.lines[ids[T_BRIEF]] = object()
        await db_session.execute(
            update(DebatOndertitel)
            .where(DebatOndertitel.id == ids[T_BRIEF])
            .values(start=now - timedelta(seconds=60), einde=now)
        )

        early = now - stemmen.WAIT + timedelta(seconds=40)
        await DebatStemmen(db_session, None, Budget.share(1)).update(
            s.id, PART, AUDIO, None, early
        )

        assert list(held.lines) == [ids[T_BRIEF]]


@pytest.mark.asyncio
class TestWhoElseLeavesTheMessageToTheTranscription:
    async def test_the_round_of_the_reactions_writes_no_turn_message(self, db_session):
        """A reaction that changes nothing a reader sees in the status
        still has the reply written again. The message of the turn is left
        to the transcription, with its count marked as out of date."""
        from tests import test_debat_vraag_status as st

        mm = st.FakeMattermost()
        s = await w._running(db_session)
        a = await w._row(db_session, s, "speaker", 60, "a", tekst=w.OPENING)
        mm.messages[a.post_id] = f"{w.KOP}\n{w.OPENING}"
        await w._marked(db_session, s, a)
        thread = await db_session.scalar(
            select(DebatMarkering.thread_post_id).where(
                DebatMarkering.sessie_id == s.id
            )
        )
        mm.messages[thread] = "oud"
        await db_session.execute(
            update(DebatMarkering)
            .where(DebatMarkering.sessie_id == s.id)
            .values(statusregel_at=_now(0), reacties_gewijzigd_at=datetime.now(UTC))
        )

        ronde = await st._ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.mislukt) == (1, 0)
        assert a.post_id not in [post_id for post_id, _ in mm.updates]
        stale = await db_session.scalar(
            select(DebatMarkering.statusregel_at).where(
                DebatMarkering.sessie_id == s.id
            )
        )
        assert stale is None

    async def test_the_count_under_the_end_of_a_debate_is_written_once(
        self, db_session
    ):
        """A toezegging from the chairman's list hangs under the message of
        the end. With the chairman's words under it, that is a message of
        the transcription too."""
        mm = w.Chat()
        s = await w._running(db_session)
        await w._row(db_session, s, "speaker", 60, "a", tekst=w.OPENING)
        await w._row(
            db_session, s, "chairman", 200, "v", post=False, tekst="Ik sluit af."
        )
        end = await w._row(db_session, s, "debate_end", 300, kop="⏹️ **Afgelopen**")
        mm.messages[end.post_id] = "⏹️ **Afgelopen**"
        await w._marked(db_session, s, end)

        await _counts(db_session, mm, s)
        writes = len(mm.updates)
        await _counts(db_session, mm, s)

        assert mm.messages[end.post_id].endswith(f"\n\n---\n{w.STATUS_EEN}")
        assert "Ik sluit af." in mm.messages[end.post_id]
        assert len(mm.updates) == writes
