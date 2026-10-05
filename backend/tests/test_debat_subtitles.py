"""Tests for reading the subtitle track of a debate.

The server is a fake that behaves like the real one: the playlist lists the
last five files, older ones are there by time, and a file that does not
exist is a 500. The spoken text is made up.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from bouwmeester.services import debat_subtitles as subs
from bouwmeester.services.debat_subtitles import NUDGE, Segment, SubtitleError

ROOM = "https://stream.example/live/zaal"
MASTER_URL = f"{ROOM}/index.m3u8?hd=1&subtitles=live"
PLAYLIST_URL = f"{ROOM}/subtitles/nl_Live.m3u8?sourcetimestamps=1&returnType=hls"
T0 = datetime(2026, 10, 5, 9, 5, 32, 880000, tzinfo=UTC)
STEP = timedelta(seconds=3.84)

MASTER = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio1",LANGUAGE="QAA",URI="stream_06/a.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=428000,AUDIO="audio1",SUBTITLES="subs"
stream_01/prog_index.m3u8
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Nederlands",DEFAULT=NO,FORCED=NO,URI="subtitles/nl_Live.m3u8?sourcetimestamps=1&returnType=hls",LANGUAGE="nl"
"""


def _vtt(*cues: tuple[str, str, str]) -> str:
    body = "WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:44302819687200\n\n"
    for start, end, text in cues:
        body += f"{start} --> {end}\n{text}\n\n"
    return body


def _grid(count: int, start: datetime = T0) -> list[datetime]:
    return [start + i * STEP for i in range(count)]


def _line(moment: datetime) -> str:
    """A playlist line the way the real one is: relative, with the chunk."""
    url = subs.segment_url(PLAYLIST_URL, moment, 3.84)
    return url.removeprefix(f"{ROOM}/subtitles/") + (
        "&SourceChunk=https://origin.example/HLS/stream_06/Segment-1.m4a?assetId=x"
    )


class Server:
    def __init__(self, existing: list[datetime], listed: list[datetime]) -> None:
        self.existing = set(existing)
        self.listed = listed
        self.requests: list[str] = []
        self.playlist_status = 200
        self.unreachable = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if self.unreachable:
            raise httpx.ConnectError("down")
        if "nl_Live.m3u8" in url:
            lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:4"]
            for moment in self.listed:
                lines += ["#EXTINF:3.840", _line(moment)]
            return httpx.Response(self.playlist_status, text="\n".join(lines))
        start = parse_qs(urlsplit(url).query)["start"][0]
        moment = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if moment not in self.existing:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(
            200, text=_vtt(("00:00:01.000", "00:00:03.000", f"zin {moment:%M%S%f}"))
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self))

    @property
    def files(self) -> int:
        return sum(".vtt" in url for url in self.requests)


class TestFindPlaylist:
    def test_the_dutch_track_of_a_stream(self):
        assert subs.find_subtitle_playlist(MASTER, MASTER_URL) == PLAYLIST_URL

    def test_a_stream_without_subtitles(self):
        master = "\n".join(x for x in MASTER.splitlines() if "SUBTITLES," not in x)

        assert subs.find_subtitle_playlist(master, MASTER_URL) is None

    def test_dutch_is_preferred_over_another_language(self):
        english = (
            '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",'
            'URI="subtitles/en_Live.m3u8",LANGUAGE="en"\n'
        )

        assert subs.find_subtitle_playlist(english + MASTER, MASTER_URL) == PLAYLIST_URL

    def test_the_only_track_is_taken_whatever_it_calls_itself(self):
        master = '#EXT-X-MEDIA:TYPE=SUBTITLES,NAME="Tekst",URI="subtitles/x.m3u8"\n'

        assert subs.find_subtitle_playlist(master, MASTER_URL) == (
            f"{ROOM}/subtitles/x.m3u8"
        )

    def test_the_audio_track_is_not_a_subtitle_track(self):
        master = MASTER.splitlines()[1] + "\n"

        assert subs.find_subtitle_playlist(master, MASTER_URL) is None


class TestParsePlaylist:
    def test_files_with_their_moment_and_address(self):
        text = "\n".join(
            ["#EXTM3U", "#EXTINF:3.840", _line(T0), "#EXTINF:3.880", _line(T0 + STEP)]
        )

        segments = subs.parse_playlist(text, PLAYLIST_URL)

        assert [s.start for s in segments] == [T0, T0 + STEP]
        assert [s.duration for s in segments] == [3.84, 3.88]
        assert segments[0].url.startswith(
            f"{ROOM}/subtitles/live/nl/20261005090532880.vtt?"
        )
        assert segments[1].end == T0 + STEP + timedelta(seconds=3.88)

    def test_a_file_without_a_moment_is_not_guessed_at(self):
        with pytest.raises(SubtitleError, match="zonder tijd"):
            subs.parse_playlist("#EXTINF:3.840\nlive/nl/x.vtt", PLAYLIST_URL)

    def test_a_moment_without_a_timezone_is_not_a_moment(self):
        line = "live/nl/x.vtt?start=2026-10-05T09:05:32.880"
        with pytest.raises(SubtitleError, match="zonder tijd"):
            subs.parse_playlist(line, PLAYLIST_URL)

    def test_an_empty_playlist(self):
        with pytest.raises(SubtitleError, match="zonder ondertitels"):
            subs.parse_playlist("#EXTM3U\n", PLAYLIST_URL)


class TestParseVtt:
    def test_lines_get_their_moment_on_the_clock(self):
        text = _vtt(
            ("00:00:03.503", "00:00:07.263", "Dit is de eerste\nzin van twee regels...")
        )

        cues = subs.parse_vtt(text, T0)

        assert cues == [
            subs.Cue(
                T0 + timedelta(seconds=3.503),
                T0 + timedelta(seconds=7.263),
                "Dit is de eerste zin van twee regels...",
            )
        ]

    def test_a_file_in_which_nobody_spoke(self):
        assert subs.parse_vtt(_vtt(), T0) == []

    def test_several_lines_in_one_file(self):
        text = _vtt(
            ("00:00:00.100", "00:00:01.000", "Een."),
            ("00:00:01.200", "00:00:05.900", "Twee."),
        )

        assert [c.text for c in subs.parse_vtt(text, T0)] == ["Een.", "Twee."]

    def test_position_on_the_screen_and_markup_are_not_text(self):
        text = (
            "WEBVTT\n\n1\n"
            "00:00:00.194 --> 00:00:04.354 line:85% position:50% align:center\n"
            "<c.wit>dat er meer</c> <b>samenhang</b> komt.\n"
        )

        cues = subs.parse_vtt(text, T0)

        assert [c.text for c in cues] == ["dat er meer samenhang komt."]
        assert cues[0].end == T0 + timedelta(seconds=4.354)

    def test_hours_and_windows_line_ends(self):
        text = "WEBVTT\r\n\r\n01:00:02.000 --> 01:00:03.000\r\nLaat.\r\n"

        assert subs.parse_vtt(text, T0)[0].start == T0 + timedelta(hours=1, seconds=2)

    def test_minutes_count(self):
        text = _vtt(("00:02:01.000", "00:02:02.500", "Later."))

        cue = subs.parse_vtt(text, T0)[0]

        assert cue.start == T0 + timedelta(minutes=2, seconds=1)
        assert cue.end == T0 + timedelta(minutes=2, seconds=2.5)

    def test_an_error_page_is_not_silence(self):
        with pytest.raises(SubtitleError, match="WebVTT"):
            subs.parse_vtt("<html>Internal Server Error</html>", T0)


def test_the_address_of_a_file_is_made_of_its_moment():
    url = subs.segment_url(PLAYLIST_URL, T0, 3.84)

    assert url == (
        f"{ROOM}/subtitles/live/nl/20261005090532880.vtt"
        "?start=2026-10-05T09%3A05%3A32.880Z&end=2026-10-05T09%3A05%3A36.720Z"
    )


def test_the_address_is_in_utc_whatever_the_moment_is_given_in():
    local = T0.astimezone(timezone(timedelta(hours=2)))

    assert subs.segment_url(PLAYLIST_URL, local, 3.84) == subs.segment_url(
        PLAYLIST_URL, T0, 3.84
    )


@pytest.mark.asyncio
class TestSegmentAt:
    async def test_on_the_grid_it_is_one_request(self):
        server = Server(_grid(3), [])
        async with server.client() as client:
            found = await subs.fetch_segment_at(client, PLAYLIST_URL, T0 + STEP)

        assert found is not None
        assert found[0].start == T0 + STEP
        assert found[1][0].start == T0 + STEP + timedelta(seconds=1)
        assert server.files == 1

    @pytest.mark.parametrize("nudges", [1, -1, 5, -5])
    async def test_after_a_jump_the_neighbouring_moments_are_tried(self, nudges):
        there = T0 + nudges * NUDGE
        server = Server([there], [])
        async with server.client() as client:
            found = await subs.fetch_segment_at(client, PLAYLIST_URL, T0)

        assert found is not None
        assert found[0].start == there
        assert found[1][0].start == there + timedelta(seconds=1)

    async def test_too_far_off_is_not_found(self):
        server = Server([T0 + 6 * NUDGE], [])
        async with server.client() as client:
            assert await subs.fetch_segment_at(client, PLAYLIST_URL, T0) is None
        assert server.files == 11

    async def test_requests_look_like_a_browser(self):
        seen: list[str] = []
        server = Server(_grid(1), [])

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["user-agent"])
            return server(request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await subs.fetch_segment_at(client, PLAYLIST_URL, T0)

        assert seen == ["Mozilla/5.0"]


@pytest.mark.asyncio
class TestFetchSince:
    async def _since(self, server, after, max_segments=100):
        async with server.client() as client:
            return await subs.fetch_since(
                client, PLAYLIST_URL, after, max_segments=max_segments
            )

    async def test_without_history_it_starts_at_the_playlist(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        cues, position = await self._since(server, None)

        assert [c.start for c in cues] == [m + timedelta(seconds=1) for m in grid[-5:]]
        assert position == grid[-1] + STEP

    async def test_without_history_it_can_start_at_a_moment_given(self):
        """Laid on the grid of the playlist, at the file that moment is in."""
        grid = _grid(20)
        server = Server(grid, grid[-5:])
        async with server.client() as client:
            cues, position = await subs.fetch_since(
                client,
                PLAYLIST_URL,
                None,
                max_segments=100,
                since=grid[3] + timedelta(seconds=1),
            )

        assert [c.start for c in cues] == [m + timedelta(seconds=1) for m in grid[3:]]
        assert position == grid[-1] + STEP

    async def test_a_moment_given_after_the_playlist_starts_is_just_the_playlist(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])
        async with server.client() as client:
            cues, _ = await subs.fetch_since(
                client, PLAYLIST_URL, None, max_segments=100, since=grid[-2]
            )

        assert len(cues) == 5

    async def test_only_what_is_new_is_fetched(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        cues, position = await self._since(server, grid[-2])

        assert len(cues) == 2
        assert server.files == 2
        assert position == grid[-1] + STEP

    async def test_nothing_new_leaves_the_position_where_it_was(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        cues, position = await self._since(server, grid[-1] + STEP)

        assert cues == []
        assert position == grid[-1] + STEP

    async def test_a_round_that_took_long_misses_nothing(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        cues, _ = await self._since(server, grid[3])

        assert [c.start for c in cues] == [m + timedelta(seconds=1) for m in grid[3:]]

    async def test_the_stretch_is_closed_across_two_jumps(self):
        first = _grid(4)
        second = _grid(4, start=first[-1] + STEP + 3 * NUDGE)
        third = _grid(8, start=second[-1] + STEP + 3 * NUDGE)
        server = Server([*first, *second, *third], third[-5:])

        cues, _ = await self._since(server, first[0])

        assert len(cues) == 16
        assert len({c.start for c in cues}) == 16

    async def test_a_listed_file_just_before_the_position_is_not_skipped(self):
        grid = _grid(10)
        server = Server(grid, grid[-5:])

        cues, _ = await self._since(server, grid[5] + NUDGE)

        assert len(cues) == 5

    async def test_just_before_the_playlist_is_no_reason_to_search(self):
        grid = _grid(10)
        server = Server(grid, grid[-5:])

        cues, _ = await self._since(server, grid[5] - NUDGE)

        assert len(cues) == 5
        assert server.files == 5

    async def test_no_more_than_asked_and_the_rest_next_time(self):
        grid = _grid(40)
        server = Server(grid, grid[-5:])

        cues, position = await self._since(server, grid[0], max_segments=8)

        assert len(cues) == 8
        assert position == grid[8]

    async def test_no_more_than_asked_from_the_playlist_either(self):
        grid = _grid(10)
        server = Server(grid, grid[-5:])

        cues, position = await self._since(server, None, max_segments=2)

        assert len(cues) == 2
        assert position == grid[-3]

    async def test_what_the_server_no_longer_has_is_skipped_not_fatal(self, caplog):
        grid = _grid(40)
        server = Server(grid[30:], grid[-5:])

        with caplog.at_level("WARNING"):
            cues, position = await self._since(server, grid[2])

        assert len(cues) == 5
        assert position == grid[-1] + STEP
        assert "niet meer op te halen" in caplog.text

    async def test_a_playlist_that_fails_raises(self):
        server = Server([], [])
        server.playlist_status = 503
        with pytest.raises(SubtitleError, match="503"):
            await self._since(server, None)

    async def test_an_unreachable_server_raises(self):
        server = Server([], [])
        server.unreachable = True
        with pytest.raises(SubtitleError, match="onbereikbaar"):
            await self._since(server, None)

    async def test_the_first_listed_file_failing_raises(self):
        grid = _grid(10)
        server = Server(grid[6:], grid[-5:])
        with pytest.raises(SubtitleError, match="500"):
            await self._since(server, None)

    async def test_a_later_listed_file_failing_keeps_what_was_read(self):
        """The next round starts at the file that failed."""
        grid = _grid(10)
        server = Server(grid[:-1], grid[-5:])

        cues, position = await self._since(server, None)

        assert len(cues) == 4
        assert position == grid[-1]

    async def test_one_missing_file_in_a_stretch_is_stepped_over(self):
        grid = _grid(30)
        server = Server([m for m in grid if m != grid[8]], grid[-5:])

        cues, position = await self._since(server, grid[2])

        assert len(cues) == 27
        assert position == grid[-1] + STEP

    async def test_three_missing_files_in_a_row_are_stepped_over_too(self):
        grid = _grid(30)
        server = Server([m for m in grid if m not in grid[8:11]], grid[-5:])

        cues, _ = await self._since(server, grid[2])

        assert len(cues) == 25

    async def test_many_missing_files_apart_are_each_stepped_over(self):
        grid = _grid(40)
        gone = {grid[5], grid[9], grid[13], grid[17], grid[21]}
        server = Server([m for m in grid if m not in gone], grid[-5:])

        cues, _ = await self._since(server, grid[2])

        assert len(cues) == 38 - 5

    async def test_four_in_a_row_is_a_cold_trail(self, caplog):
        grid = _grid(30)
        server = Server([m for m in grid if m not in grid[8:12]], grid[-5:])

        with caplog.at_level("WARNING"):
            cues, position = await self._since(server, grid[2])

        assert len(cues) == 6 + 5
        assert position == grid[-1] + STEP
        assert "niet meer op te halen" in caplog.text

    async def test_an_address_that_is_no_address_is_a_subtitle_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.InvalidURL("nope")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(SubtitleError, match="onbereikbaar"):
                await subs.fetch_text(client, PLAYLIST_URL)


class TestSamePlace:
    """The playlists are not ours; an address in one is not followed
    anywhere else."""

    @pytest.mark.parametrize(
        "uri",
        [
            "http://stream.example/live/zaal/subtitles/nl.m3u8",
            "https://elsewhere.example/nl.m3u8",
            "http://169.254.169.254/latest/meta-data",
        ],
    )
    def test_a_track_somewhere_else_is_not_a_track(self, uri):
        master = f'#EXT-X-MEDIA:TYPE=SUBTITLES,LANGUAGE="nl",URI="{uri}"\n'

        assert subs.find_subtitle_playlist(master, MASTER_URL) is None

    def test_a_full_address_on_the_same_server_is_fine(self):
        master = f'#EXT-X-MEDIA:TYPE=SUBTITLES,LANGUAGE="nl",URI="{PLAYLIST_URL}"\n'

        assert subs.find_subtitle_playlist(master, MASTER_URL) == PLAYLIST_URL

    @pytest.mark.parametrize(
        "line",
        [
            "http://stream.example/x.vtt?start=2026-10-05T09:05:32.880Z",
            "https://10.0.0.1/x.vtt?start=2026-10-05T09:05:32.880Z",
        ],
    )
    def test_a_file_somewhere_else_is_not_fetched(self, line):
        with pytest.raises(SubtitleError, match="ander adres"):
            subs.parse_playlist(f"#EXTINF:3.840\n{line}", PLAYLIST_URL)


def test_a_segment_ends_after_its_length():
    assert Segment(T0, "x").end == T0 + STEP
