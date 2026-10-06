"""Tests for when in a turn a question was asked, and the link to it."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from bouwmeester.services.debat_transcript import append_text
from bouwmeester.services.debat_vraag_moment import (
    LEAD_IN,
    SAFE_URL,
    Line,
    moment_of_position,
    question_url,
)

START = datetime.fromisoformat("2026-10-06T21:45:00+02:00")
# The expression the player of Debat Direct reads the `event` parameter
# with, as it stands in the script of the site.
PLAYER = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))$"
)
TURN_URL = (
    "https://debatdirect.example/2026-10-06/wonen/plenaire-zaal/een-debat"
    "?event=speaker2026-10-06T21%3A45%3A00%2B0200"
)


def _at(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def _lines(*texts: str, step: float = 4) -> tuple[Line, ...]:
    return tuple(Line(_at(10 + step * n), text) for n, text in enumerate(texts))


def _turn(*rows: list[str]) -> str:
    """The text of a turn, joined the way the database and `Turn.text` do:
    one space between the lines of a row, rows stripped and one space."""
    text = ""
    for row in rows:
        text = append_text(text, " ".join(row))
    return text


class TestMomentOfPosition:
    LINES = _lines(
        "Voorzitter, dank u wel.",
        "Ik heb een vraag over de woningbouw.",
        "Kan de minister zeggen",
        "wanneer de brief komt?",
    )
    TEXT = _turn([line.text for line in LINES])

    def test_the_line_a_position_is_in(self):
        at = self.TEXT.index("Kan de minister")
        assert moment_of_position(self.LINES, self.TEXT, at) == _at(18)

    def test_the_first_and_the_last_character_of_a_line(self):
        first = self.TEXT.index("Ik heb")
        last = self.TEXT.index("woningbouw.") + len("woningbouw.") - 1
        assert moment_of_position(self.LINES, self.TEXT, first) == _at(14)
        assert moment_of_position(self.LINES, self.TEXT, last) == _at(14)
        assert moment_of_position(self.LINES, self.TEXT, last + 2) == _at(18)

    def test_the_very_first_and_the_very_last_character(self):
        assert moment_of_position(self.LINES, self.TEXT, 0) == _at(10)
        assert moment_of_position(self.LINES, self.TEXT, len(self.TEXT) - 1) == _at(22)

    def test_halfway_a_line_is_that_line(self):
        at = self.TEXT.index("de brief komt")
        assert moment_of_position(self.LINES, self.TEXT, at) == _at(22)

    def test_the_space_between_two_lines_is_the_line_after_it(self):
        at = self.TEXT.index(" Kan de minister")
        assert moment_of_position(self.LINES, self.TEXT, at) == _at(18)

    @pytest.mark.parametrize("position", [-1, 10_000])
    def test_a_position_outside_the_text(self, position):
        assert moment_of_position(self.LINES, self.TEXT, position) is None
        assert moment_of_position(self.LINES, self.TEXT, len(self.TEXT)) is None

    def test_without_lines_there_is_no_moment(self):
        assert moment_of_position((), self.TEXT, 5) is None

    def test_lines_that_are_not_this_text_say_nothing(self):
        """A line moved to another turn after the text was read, or a row
        from before lines were kept: a moment from other words would look
        exact and be wrong."""
        at = self.TEXT.index("Kan de minister")
        assert moment_of_position(self.LINES[:-1], self.TEXT, at) is None
        assert moment_of_position(self.LINES[1:], self.TEXT, at) is None
        other = (*self.LINES[:-1], Line(_at(22), "wanneer de brief kwam?"))
        assert moment_of_position(other, self.TEXT, at) is None

    def test_a_turn_of_several_rows(self):
        """The same speaker carrying on after a word of the chairman: the
        rows are stripped and joined, the lines within a row are not."""
        rows = [
            ["  Voorzitter. ", " Dank u wel.  "],
            ["  Kan de minister dat ", "toezeggen?  "],
        ]
        lines = _lines(*rows[0], *rows[1])
        text = _turn(*rows)
        assert text == "Voorzitter.   Dank u wel. Kan de minister dat  toezeggen?"
        assert moment_of_position(lines, text, text.index("Dank")) == _at(14)
        assert moment_of_position(lines, text, text.index("Kan")) == _at(18)
        assert moment_of_position(lines, text, text.index("toezeggen")) == _at(22)

    def test_an_empty_line_is_nobodys_moment(self):
        lines = _lines("Eerste zin.", "", "   ", "Tweede zin.")
        text = _turn([line.text for line in lines])
        assert moment_of_position(lines, text, text.index("Tweede")) == _at(22)
        assert moment_of_position(lines, text, text.index("zin.")) == _at(10)


class TestQuestionUrl:
    def test_the_link_of_the_turn_at_the_moment_of_the_question(self):
        url = question_url(TURN_URL, _at(612), START)

        # 21:55:12, five seconds early, as the feed writes a moment.
        assert url == (
            "https://debatdirect.example/2026-10-06/wonen/plenaire-zaal/een-debat"
            "?event=speaker2026-10-06T21%3A55%3A07%2B0200"
        )

    def test_the_player_of_the_site_reads_the_intended_moment(self):
        url = question_url(TURN_URL, _at(612), START)

        (event,) = parse_qs(urlsplit(url).query)["event"]
        read = PLAYER.search(event)
        assert read is not None
        assert event == f"speaker{read.group(1)}"
        moment = datetime.strptime(read.group(1), "%Y-%m-%dT%H:%M:%S%z")
        assert moment == _at(612) - LEAD_IN
        assert LEAD_IN == timedelta(seconds=5)

    def test_never_before_the_turn_began(self):
        for seconds in (0, 3, 5):
            url = question_url(TURN_URL, _at(seconds), START)
            assert url == TURN_URL
        assert question_url(TURN_URL, _at(6), START).endswith("T21%3A45%3A01%2B0200")
        assert question_url(TURN_URL, _at(-30), START) == TURN_URL

    def test_local_time_whatever_zone_the_moment_is_in(self):
        utc = datetime.fromisoformat("2026-10-06T19:55:12+00:00")
        assert question_url(TURN_URL, utc, START).endswith(
            "speaker2026-10-06T21%3A55%3A07%2B0200"
        )
        winter = datetime.fromisoformat("2026-12-01T10:00:00+00:00")
        assert question_url(TURN_URL, winter, START).endswith(
            "speaker2026-12-01T10%3A59%3A55%2B0100"
        )

    def test_a_fraction_of_a_second_is_rounded_down(self):
        url = question_url(TURN_URL, _at(612.9), START)
        assert url.endswith("T21%3A55%3A07%2B0200")

    @pytest.mark.parametrize(
        "stamp",
        [
            "2026-10-06T21%3A45%3A00%2B0200",
            "2026-10-06T21%3A45%3A00%2B02%3A00",
            "2026-10-06T21%3A45%3A00.123%2B0200",
            "2026-10-06T19%3A45%3A00Z",
            "2026-10-06T21:45:00%2B0200",
        ],
    )
    def test_however_the_link_of_the_turn_wrote_its_moment(self, stamp):
        url = question_url(
            f"https://debatdirect.example/d?event=interrupter{stamp}", _at(612), START
        )
        assert url == (
            "https://debatdirect.example/d"
            "?event=interrupter2026-10-06T21%3A55%3A07%2B0200"
        )

    def test_the_rest_of_the_link_stays_as_it_was(self):
        url = question_url(
            "https://debatdirect.example/a%20b/c?x=1%2B1"
            "&event=speaker2026-10-06T21%3A45%3A00%2B0200&y=2#top",
            _at(612),
            START,
        )
        assert url == (
            "https://debatdirect.example/a%20b/c?x=1%2B1"
            "&event=speaker2026-10-06T21%3A55%3A07%2B0200&y=2#top"
        )

    @pytest.mark.parametrize(
        "url",
        [
            None,
            "",
            "https://debatdirect.example/d",
            "https://debatdirect.example/d?event=speaker1",
            "https://debatdirect.example/d?event=",
            # The moment has to be the end of the value, as the player wants.
            "https://debatdirect.example/d?event=2026-10-06T21%3A45%3A00%2B0200x",
            # Another parameter that only ends in "event".
            "https://debatdirect.example/d?noevent=speaker2026-10-06T21%3A45%3A00Z",
        ],
    )
    def test_a_link_without_a_moment_to_replace(self, url):
        assert question_url(url, _at(612), START) is None

    @pytest.mark.parametrize(
        "url",
        [
            "http://debatdirect.example/d?event=speaker2026-10-06T21%3A45%3A00Z",
            "javascript:alert(1)?event=speaker2026-10-06T21%3A45%3A00Z",
            "https://debatdirect.example/d) [klik](https://kwaad.example"
            "?event=speaker2026-10-06T21%3A45%3A00Z",
            "https://debatdirect.example/d?event=speaker2026-10-06T21%3A45%3A00Z"
            "&x=) [klik](y",
        ],
    )
    def test_a_link_that_is_not_safe_to_post_stays_unsafe(self, url):
        assert question_url(url, _at(612), START) is None

    def test_what_is_in_front_of_the_moment_cannot_break_out_of_the_link(self):
        """The kind of event is decoded and encoded again. Whatever it
        holds comes back encoded, never as a bracket."""
        url = question_url(
            "https://debatdirect.example/d"
            "?event=%29%20%5Bklik%5D%28x2026-10-06T21%3A45%3A00Z",
            _at(612),
            START,
        )
        assert url is not None
        assert SAFE_URL.match(url)
        assert "(" not in url and ")" not in url and "[" not in url
