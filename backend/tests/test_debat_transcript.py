"""Tests for the text of a debate under the messages of the timeline.

First the parts that only compute: which line belongs to which turn, and
where a long turn is cut. Then the whole thing against a real database, with
the made-up debates and the fake Mattermost of the timeline tests, and
subtitles that come in half a minute behind like the real ones.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from sqlalchemy import select

from bouwmeester.core.config import get_settings
from bouwmeester.models.debat_sessie import DebatSpreekbeurt
from bouwmeester.services import debat_subtitles as subs
from bouwmeester.services.debat_subtitles import Cue
from bouwmeester.services.debat_tijdlijn_service import (
    DebatTijdlijnService,
    TickResult,
)
from bouwmeester.services.debat_transcript import (
    MESSAGE_LIMIT,
    append_text,
    assign_cues,
    fit_messages,
    render,
    split_text,
)
from bouwmeester.services.debat_transcript_service import DebatTranscript
from tests.test_debat_tijdlijn import (
    START,
    FakeMattermost,
    Feed,
    _debat,
    _run,
    _sessie,
)

STREAM = "https://stream.example/live/zaal/index.m3u8"
PLAYLIST = "https://stream.example/live/zaal/subtitles/nl_Live.m3u8"
MASTER = f'#EXTM3U\n#EXT-X-MEDIA:TYPE=SUBTITLES,LANGUAGE="nl",URI="{PLAYLIST}"\n'
OFFSET = timedelta(seconds=2)
# The subtitle track lists a file about this long after its moment.
BEHIND = timedelta(seconds=35)


def _cue(seconds: float, text: str, length: float = 2.0) -> Cue:
    start = START + timedelta(seconds=seconds)
    return Cue(start, start + timedelta(seconds=length), text)


class TestAssignCues:
    def test_a_line_belongs_to_the_turn_it_was_spoken_in(self):
        turns = [("a", START), ("b", START + timedelta(seconds=60))]
        cues = [_cue(5, "Een."), _cue(30, "Twee."), _cue(61, "Drie.")]

        assert assign_cues(cues, turns) == {"a": "Een. Twee.", "b": "Drie."}

    def test_the_sound_is_later_than_the_event(self):
        turns = [("a", START), ("b", START + timedelta(seconds=60))]
        cues = [_cue(61, "Nog van a."), _cue(62, "Van b.")]

        assert assign_cues(cues, turns, OFFSET) == {"a": "Nog van a.", "b": "Van b."}

    def test_a_line_before_the_first_turn_is_nobodys(self):
        assert assign_cues([_cue(-5, "Vooraf.")], [("a", START)]) == {}

    def test_a_turn_without_lines_is_not_in_the_answer(self):
        turns = [("a", START), ("b", START + timedelta(seconds=10))]

        assert assign_cues([_cue(20, "Alleen b.")], turns) == {"b": "Alleen b."}

    def test_lines_are_put_in_order_of_time(self):
        cues = [_cue(9, "Later."), _cue(3, "Eerder.")]

        assert assign_cues(cues, [("a", START)]) == {"a": "Eerder. Later."}

    def test_no_turns_no_text(self):
        assert assign_cues([_cue(3, "Iets.")], []) == {}


class TestAppendText:
    def test_more_text_goes_behind_with_a_space(self):
        assert append_text("Een.", "Twee.") == "Een. Twee."

    def test_the_first_text(self):
        assert append_text(None, " Een. ") == "Een."

    def test_nothing_new_changes_nothing(self):
        assert append_text("Een.", "  ") == "Een."

    def test_dots_of_a_line_that_runs_on_are_dropped(self):
        assert append_text("dat we toewerken naar...", "een steunpunt.") == (
            "dat we toewerken naar een steunpunt."
        )

    def test_dots_inside_what_comes_in_are_dropped_too(self):
        assert append_text("Voorzitter.", "een overleg... en dat is goed.") == (
            "Voorzitter. een overleg en dat is goed."
        )

    def test_dots_before_a_new_sentence_stay(self):
        assert append_text("En toen...", "Voorzitter.") == "En toen... Voorzitter."


class TestSplitText:
    def test_a_short_text_is_one_piece(self):
        assert split_text("Een korte zin.") == ["Een korte zin."]

    def test_no_text_is_one_empty_piece(self):
        assert split_text("") == [""]

    def test_a_cut_falls_after_the_last_sentence_that_fits(self):
        text = "Eerste zin hier. Tweede zin hier. Derde zin hier."

        assert split_text(text, limit=40, minimum=5) == [
            "Eerste zin hier. Tweede zin hier.",
            "Derde zin hier.",
        ]

    def test_a_question_mark_ends_a_sentence_too(self):
        text = "Is dat zo? Dat lijkt mij niet het geval te zijn, voorzitter."

        assert split_text(text, limit=30, minimum=5)[0] == "Is dat zo?"

    def test_not_before_the_minimum(self):
        text = "Kort. " + "woord " * 20

        pieces = split_text(text, limit=60, minimum=30)

        assert len(pieces[0]) > 30
        assert not pieces[0].endswith("Kort.")

    def test_without_a_sentence_end_the_cut_is_at_a_space(self):
        pieces = split_text("woord " * 30, limit=50, minimum=10)

        assert all(len(p) <= 50 for p in pieces)
        assert " ".join(pieces) == ("woord " * 30).strip()

    def test_one_endless_word_is_cut_anyway(self):
        pieces = split_text("x" * 100, limit=40, minimum=10)

        assert [len(p) for p in pieces] == [40, 40, 20]

    def test_nothing_is_lost_and_every_piece_fits(self):
        text = " ".join(f"Dit is zin nummer {i} van de spreker." for i in range(300))

        pieces = split_text(text)

        assert " ".join(pieces) == text
        assert all(len(p) <= MESSAGE_LIMIT for p in pieces)
        assert len(pieces) > 3

    def test_a_text_that_grows_keeps_its_cuts(self):
        """Otherwise a message that was full is rewritten, and what was
        read there a minute ago is suddenly somewhere else."""
        sentences = [f"Dit is zin nummer {i} van de spreker." for i in range(400)]
        earlier: list[str] = []
        for count in range(40, 400, 7):
            pieces = split_text(" ".join(sentences[:count]))
            assert pieces[: len(earlier) - 1] == earlier[:-1]
            earlier = pieces

    def test_a_sentence_ending_exactly_at_the_limit_fits(self):
        text = "a" * 39 + ". " + "b" * 20

        assert split_text(text, limit=40, minimum=5) == ["a" * 39 + ".", "b" * 20]

    def test_the_sentence_that_ends_at_the_limit_wins_from_an_earlier_one(self):
        text = "Eerste. " + "a" * 31 + ". " + "b" * 20

        assert split_text(text, limit=40, minimum=5) == [
            "Eerste. " + "a" * 31 + ".",
            "b" * 20,
        ]


class TestFitMessages:
    def test_enough_room_changes_nothing(self):
        assert fit_messages(["a", "b"], 2) == ["a", "b"]

    def test_the_last_message_takes_what_does_not_fit(self):
        assert fit_messages(["a", "b", "c", "d"], 2) == ["a", "b c d"]

    def test_one_message_takes_everything(self):
        assert fit_messages(["a", "b"], 1) == ["a b"]


class TestRender:
    def test_the_text_comes_under_the_first_line(self):
        assert render("**Kamerlid A (X)** · 10:42", "Voorzitter.") == (
            "**Kamerlid A (X)** · 10:42\nVoorzitter."
        )

    def test_without_text_it_is_the_first_line_alone(self):
        assert render("**Kamerlid A (X)** · 10:42", "") == "**Kamerlid A (X)** · 10:42"

    def test_a_next_message_says_it_continues(self):
        assert render("**Kamerlid A (X)** · 10:42", "En verder.", vervolg=True) == (
            "**Kamerlid A (X)** · 10:42 · vervolg\nEn verder."
        )

    def test_what_was_said_cannot_mention_or_format(self):
        message = render("kop", "@all kijk naar *dit* en _dat_")

        assert "@all" not in message.replace("\\@all", "")
        assert "*dit*" not in message


class Subtitles:
    """The subtitle track at a moment in time."""

    def __init__(self, monkeypatch, feed: Feed, cues: list[Cue]) -> None:
        self.feed = feed
        self.cues = cues
        self.master = MASTER
        self.error = False
        self.reads: list[tuple] = []
        self.masters = 0

        async def fetch_text(client, url):
            self.masters += 1
            if self.error:
                raise subs.SubtitleError("down")
            return self.master

        async def fetch_since(client, url, after, *, max_segments, since=None):
            self.reads.append((url, after, since))
            if self.error:
                raise subs.SubtitleError("down")
            upto = self.feed.now - BEHIND
            begin = after or since or upto
            if upto <= begin:
                return [], after
            return [c for c in self.cues if begin <= c.start < upto], upto

        monkeypatch.setattr(subs, "fetch_text", fetch_text)
        monkeypatch.setattr(subs, "fetch_since", fetch_since)


class Mattermost(FakeMattermost):
    """Also remembers what every message says now, and every rewrite."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: dict[str, str] = {}
        self.order: list[str] = []
        self.updates: list[tuple[str, str]] = []
        self.fail_updates = 0

    async def send_channel_message(self, channel_id, text, props=None, root_id=None):
        post_id = await super().send_channel_message(channel_id, text, props, root_id)
        if post_id:
            self.messages[post_id] = text
            self.order.append(post_id)
        return post_id

    async def update_post(self, post_id, message, props=None) -> bool:
        if self.fail_updates > 0:
            self.fail_updates -= 1
            return False
        self.updates.append((post_id, message))
        self.messages[post_id] = message
        return True

    @property
    def channel(self) -> list[str]:
        return [self.messages[post_id] for post_id in self.order]


def _stream(debat):
    return dataclasses.replace(debat, stream_url=STREAM, stream_offset=OFFSET)


def _minutes(minutes: float) -> timedelta:
    return timedelta(minutes=minutes)


async def _play(db_session, mm, feed, until: float, start: float = -10, step: int = 10):
    await _run(
        db_session, mm, feed, START + _minutes(start), START + _minutes(until), step
    )


@pytest.mark.asyncio
class TestTranscript:
    async def test_what_is_said_comes_under_who_says_it(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        Subtitles(
            monkeypatch,
            feed,
            [_cue(65, "Voorzitter, dank."), _cue(70, "Ik heb een vraag.")],
        )
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 3)

        assert mm.channel[-1].startswith("**Onbekende spreker** · [")
        assert mm.channel[-1].endswith("\nVoorzitter, dank. Ik heb een vraag.")
        assert len(mm.channel) == 2

    async def test_the_message_grows_while_someone_speaks(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        Subtitles(
            monkeypatch, feed, [_cue(65, "Een."), _cue(95, "Twee."), _cue(125, "Drie.")]
        )
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 4)

        bodies = [text.split("\n", 1)[1] for _, text in mm.updates]
        assert bodies == ["Een.", "Een. Twee.", "Een. Twee. Drie."]
        assert len({post_id for post_id, _ in mm.updates}) == 1

    async def test_an_interruption_gets_its_own_words(self, db_session, monkeypatch):
        debat = _debat(
            ("speaker", 1, "a"), ("interrupter", 2, "b"), ("speaker", 3, "a")
        )
        feed = Feed(monkeypatch, parts=[_stream(debat)])
        cues = [
            _cue(70, "Mijn betoog."),
            _cue(125, "Mag ik iets vragen?"),
            _cue(185, "Zeker."),
        ]
        Subtitles(monkeypatch, feed, cues)
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 5)

        assert [m.split("\n", 1)[1] for m in mm.channel[1:]] == [
            "Mijn betoog.",
            "Mag ik iets vragen?",
            "Zeker.",
        ]
        assert mm.channel[2].startswith("↳ ")

    async def test_the_offset_of_the_stream_decides_at_the_edge(
        self, db_session, monkeypatch
    ):
        """A line one second after the event is still the speaker before:
        the sound runs two seconds behind the events."""
        debat = _debat(("speaker", 1, "a"), ("speaker", 2, "b"))
        feed = Feed(monkeypatch, parts=[_stream(debat)])
        Subtitles(
            monkeypatch, feed, [_cue(121, "Slotzin van a."), _cue(123, "Begin van b.")]
        )
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 4)

        assert mm.channel[1].endswith("\nSlotzin van a.")
        assert mm.channel[2].endswith("\nBegin van b.")

    async def test_a_speaker_who_carries_on_keeps_one_message(
        self, db_session, monkeypatch
    ):
        """The chairman says a word in between. That is not shown, and
        what the speaker says after it goes on in the same message."""
        debat = _debat(("speaker", 1, "a"), ("chairman", 2, "v"), ("speaker", 3, "a"))
        feed = Feed(monkeypatch, parts=[_stream(debat)])
        cues = [
            _cue(70, "Eerste deel."),
            _cue(125, "Gaat u verder."),
            _cue(185, "Tweede deel."),
        ]
        Subtitles(monkeypatch, feed, cues)
        mm = Mattermost()
        sessie = await _sessie(db_session)

        await _play(db_session, mm, feed, 5)

        assert len(mm.channel) == 2
        assert mm.channel[1].endswith("\nEerste deel. Tweede deel.")
        kept = (
            await db_session.execute(
                select(DebatSpreekbeurt.tekst).where(
                    DebatSpreekbeurt.sessie_id == sessie.id,
                    DebatSpreekbeurt.event_type == "chairman",
                )
            )
        ).scalar_one()
        assert kept == "Gaat u verder."

    async def test_a_long_turn_continues_in_a_next_message(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        cues = [
            _cue(65 + 4 * i, f"Dit is zin nummer {i} van het betoog.")
            for i in range(120)
        ]
        Subtitles(monkeypatch, feed, cues)
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 11)

        turn = mm.channel[1:]
        assert len(turn) == 3
        assert all(len(m.split("\n", 1)[1]) <= MESSAGE_LIMIT for m in turn)
        assert " · vervolg\n" not in turn[0]
        assert all(" · vervolg\n" in m for m in turn[1:])
        said = " ".join(m.split("\n", 1)[1] for m in turn)
        assert said == " ".join(c.text for c in cues)

    async def test_a_full_message_is_not_written_again(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        cues = [
            _cue(65 + 4 * i, f"Dit is zin nummer {i} van het betoog.")
            for i in range(120)
        ]
        Subtitles(monkeypatch, feed, cues)
        mm = Mattermost()
        await _sessie(db_session)
        await _play(db_session, mm, feed, 6)
        assert len(mm.channel) == 3
        first = mm.order[1]
        mm.updates.clear()

        await _play(db_session, mm, feed, 11, start=6.2)

        assert mm.updates
        assert first not in {post_id for post_id, _ in mm.updates}

    async def test_late_words_do_not_start_a_message_below_the_next_speaker(
        self, db_session, monkeypatch
    ):
        """The text runs half a minute behind. When it overflows after
        someone else already has a message, it stays where it is."""
        debat = _debat(("speaker", 1, "a"), ("speaker", 3, "b"))
        feed = Feed(monkeypatch, parts=[_stream(debat)])
        cues = [
            _cue(63 + 2 * i, f"Dit is zin nummer {i} van het betoog.")
            for i in range(58)
        ]
        Subtitles(monkeypatch, feed, cues)
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 5)

        assert len(mm.channel) == 3
        assert mm.channel[2].startswith("**Onbekende spreker**")
        assert " · vervolg" not in mm.channel[2]
        assert mm.channel[1].endswith("nummer 57 van het betoog.")
        assert len(mm.channel[1]) > MESSAGE_LIMIT

    async def test_a_rewrite_that_fails_is_done_the_next_round(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, [_cue(65, "Een."), _cue(70, "Twee.")])
        mm = Mattermost()
        await _sessie(db_session)
        await _play(db_session, mm, feed, 1.5)

        mm.fail_updates = 3
        feed.now = START + _minutes(2)
        result = await DebatTijdlijnService(db_session, mm).tick(feed.now)
        assert result.fouten == 1
        assert "\n" not in mm.channel[1]

        mm.fail_updates = 0
        await _play(db_session, mm, feed, 2.5, start=2.2)

        assert mm.channel[1].endswith("\nEen. Twee.")

    async def test_a_restart_reads_nothing_twice(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        track = Subtitles(monkeypatch, feed, [_cue(65, "Een."), _cue(95, "Twee.")])
        mm = Mattermost()
        await _sessie(db_session)
        await _play(db_session, mm, feed, 3)
        before = len(mm.updates)

        await _play(db_session, mm, feed, 4, start=3.2)

        assert mm.channel[1].endswith("\nEen. Twee.")
        assert len(mm.updates) == before
        assert track.masters == 1

    async def test_the_first_reading_goes_back_to_the_start_of_the_debate(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        track = Subtitles(monkeypatch, feed, [])
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 1)

        url, after, since = track.reads[0]
        assert (url, after, since) == (PLAYLIST, None, START)

    async def test_joining_late_reads_back_ten_minutes_at_most(
        self, db_session, monkeypatch
    ):
        feed = Feed(
            monkeypatch,
            parts=[_stream(_debat(("speaker", 1, "a"), ("speaker", 40, "b")))],
        )
        track = Subtitles(monkeypatch, feed, [])
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 41, start=40.5)

        assert track.reads[0][2] == track.feed.now - timedelta(minutes=10) or (
            START + _minutes(30) < track.reads[0][2] < START + _minutes(31.5)
        )

    async def test_a_stream_without_subtitles_is_asked_once(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        track = Subtitles(monkeypatch, feed, [_cue(65, "Een.")])
        track.master = "#EXTM3U\n"
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 3)

        assert track.masters == 1
        assert track.reads == []
        assert mm.updates == []
        assert len(mm.channel) == 2

    async def test_subtitles_that_cannot_be_read_do_not_stop_the_timeline(
        self, db_session, monkeypatch
    ):
        debat = _debat(("speaker", 1, "a"), ("speaker", 2, "b"))
        feed = Feed(monkeypatch, parts=[_stream(debat)])
        track = Subtitles(monkeypatch, feed, [_cue(65, "Een.")])
        track.error = True
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 3)
        feed.now = START + _minutes(3.2)
        result = await DebatTijdlijnService(db_session, mm).tick(feed.now)

        assert len(mm.channel) == 3
        assert result.fouten == 0

        track.error = False
        await _play(db_session, mm, feed, 4, start=3.4)
        assert mm.channel[1].endswith("\nEen.")

    async def test_a_debate_without_a_stream_has_just_its_timeline(
        self, db_session, monkeypatch
    ):
        feed = Feed(monkeypatch, parts=[_debat(("speaker", 1, "a"))])
        track = Subtitles(monkeypatch, feed, [_cue(65, "Een.")])
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 3)

        assert track.masters == 0
        assert mm.updates == []

    async def test_switched_off_leaves_the_timeline_as_it_was(
        self, db_session, monkeypatch
    ):
        monkeypatch.setattr(get_settings(), "DEBAT_TRANSCRIPT_ENABLED", False)
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        track = Subtitles(monkeypatch, feed, [_cue(65, "Een.")])
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 3)

        assert track.masters == 0
        assert mm.updates == []

    async def test_reading_stops_a_while_after_the_end(self, db_session, monkeypatch):
        debat = _debat(("speaker", 1, "a"), ("debate_end", 3, ""))
        feed = Feed(monkeypatch, parts=[_stream(debat)])
        track = Subtitles(
            monkeypatch, feed, [_cue(65, "Een."), _cue(175, "Laatste woorden.")]
        )
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 6)
        reads = len(track.reads)
        await _play(db_session, mm, feed, 9, start=6.2)

        assert mm.channel[1].endswith("\nEen. Laatste woorden.")
        assert len(track.reads) == reads

    async def test_a_turn_the_timeline_missed_does_not_end_up_with_someone_else(
        self, db_session, monkeypatch
    ):
        """Rows without a message, from a stretch that was missed, can have
        text too. It belongs to nobody's message: not to the speaker before
        the stretch, and what that speaker says after it is a new turn."""
        mm = Mattermost()
        sessie = await _sessie(db_session)
        post_id = await mm.send_channel_message(sessie.channel_id, "kop a")
        rows = [
            ("speaker", 1, "a", post_id, "kop a", "Van a."),
            ("speaker", 5, "b", None, None, "Van b."),
            ("speaker", 9, "a", None, None, "Weer a."),
        ]
        for kind, minute, who, post, kop, tekst in rows:
            db_session.add(
                DebatSpreekbeurt(
                    sessie_id=sessie.id,
                    debat_direct_id="d1",
                    event_type=kind,
                    event_start=START + _minutes(minute),
                    object_id=who,
                    post_id=post,
                    kop=kop,
                    tekst=tekst,
                )
            )
        await db_session.flush()

        await DebatTranscript(db_session, mm)._write(
            sessie.id, sessie.channel_id, "d1", TickResult()
        )

        assert mm.channel == ["kop a\nVan a."]

    async def test_what_was_said_cannot_mention_anyone(self, db_session, monkeypatch):
        feed = Feed(monkeypatch, parts=[_stream(_debat(("speaker", 1, "a")))])
        Subtitles(monkeypatch, feed, [_cue(65, "Schrijf naar @channel en @all.")])
        mm = Mattermost()
        await _sessie(db_session)

        await _play(db_session, mm, feed, 3)

        assert "\\@channel" in mm.channel[1]
        assert "\\@all" in mm.channel[1]
