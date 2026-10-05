"""Tests for fetching the audio of a debate, segment by segment.

The server is a fake that knows which segments exist, the way the real one
does: the playlist lists the last five, older ones are there by name for a
while, and anything else is a 404.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from bouwmeester.services import debat_audio as audio
from bouwmeester.services.debat_audio import (
    NUDGE_TICKS,
    SEGMENT_TICKS,
    AudioError,
    Segment,
)

BASE = "https://stream.example/live/zaal/audio"
PLAYLIST_URL = f"{BASE}/prog_index.m3u8"
T0 = 17_911_872_000_000_000


def _playlist_text(ticks: list[int], durations: list[float] | None = None) -> str:
    durations = durations or [3.84] * len(ticks)
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-TARGETDURATION:4",
        f'#EXT-X-MAP:URI="{BASE}/init.m4i"',
    ]
    for tick, duration in zip(ticks, durations, strict=True):
        lines.append(f"#EXTINF:{duration},")
        lines.append(f"{BASE}/Segment-{tick}.m4a")
    return "\n".join(lines) + "\n"


class Server:
    """Which segments exist, and every request that was made."""

    def __init__(self, existing: list[int], listed: list[int]) -> None:
        self.existing = set(existing)
        self.listed = listed
        self.requests: list[str] = []
        self.status: dict[str, int] = {}
        self.unreachable = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if self.unreachable:
            raise httpx.ConnectError("down")
        if url in self.status:
            return httpx.Response(self.status[url])
        if url == PLAYLIST_URL:
            return httpx.Response(200, text=_playlist_text(self.listed))
        name = url.rsplit("/", 1)[1]
        if name.startswith("Segment-"):
            tick = int(name[len("Segment-") : -len(".m4a")])
            if tick in self.existing:
                return httpx.Response(200, content=f"<{tick}>".encode())
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self))


def _grid(count: int, start: int = T0) -> list[int]:
    return [start + i * SEGMENT_TICKS for i in range(count)]


class TestTime:
    def test_a_segment_name_is_a_moment(self):
        moment = datetime(2026, 10, 5, 8, 4, 30, 400000, tzinfo=UTC)
        ticks = audio.datetime_to_ticks(moment)

        assert ticks == 17_911_874_704_000_000
        assert audio.ticks_to_datetime(ticks) == moment

    def test_a_segment_ends_where_the_next_one_starts(self):
        segment = Segment(T0, "x")

        assert segment.end_ticks == T0 + SEGMENT_TICKS
        assert (segment.end - segment.start).total_seconds() == 3.84

    def test_a_longer_segment_ends_later(self):
        assert Segment(T0, "x", 3.88).end_ticks == T0 + SEGMENT_TICKS + NUDGE_TICKS


class TestParsePlaylist:
    def test_segments_with_their_time_and_length(self):
        ticks = _grid(5)
        playlist = audio.parse_playlist(
            _playlist_text(ticks, [3.84, 3.84, 3.88, 3.84, 3.84])
        )

        assert playlist.init_url == f"{BASE}/init.m4i"
        assert [s.ticks for s in playlist.segments] == ticks
        assert [s.duration for s in playlist.segments] == [3.84, 3.84, 3.88, 3.84, 3.84]
        assert playlist.segments[0].url == f"{BASE}/Segment-{T0}.m4a"
        assert playlist.base_url == BASE

    def test_without_an_init_section_it_cannot_be_played(self):
        text = _playlist_text(_grid(2)).replace("#EXT-X-MAP", "#EXT-X-NOPE")
        with pytest.raises(AudioError, match="init"):
            audio.parse_playlist(text)

    def test_the_placeholder_of_an_empty_room_is_not_audio_of_a_debate(self):
        text = _playlist_text(_grid(2)).replace(f"Segment-{T0}", "filler-0001")
        with pytest.raises(AudioError, match="tijd"):
            audio.parse_playlist(text)

    def test_a_playlist_without_segments(self):
        with pytest.raises(AudioError, match="zonder segmenten"):
            audio.parse_playlist(_playlist_text([]))

    def test_an_unreadable_length_falls_back_to_the_usual_one(self):
        text = _playlist_text(_grid(1)).replace("#EXTINF:3.84,", "#EXTINF:abc,")

        assert audio.parse_playlist(text).segments[0].duration == 3.84


@pytest.mark.asyncio
class TestFetch:
    async def test_playlist_is_read_like_a_browser(self):
        server = Server(_grid(5), _grid(5))
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["user-agent"])
            return server(request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            playlist = await audio.fetch_playlist(client, PLAYLIST_URL)

        assert len(playlist.segments) == 5
        assert seen == ["Mozilla/5.0"]

    async def test_a_playlist_that_is_not_there(self):
        server = Server([], [])
        server.status[PLAYLIST_URL] = 503
        async with server.client() as client:
            with pytest.raises(AudioError, match="503"):
                await audio.fetch_playlist(client, PLAYLIST_URL)

    async def test_an_unreachable_server_is_an_audio_error(self):
        server = Server([], [])
        server.unreachable = True
        async with server.client() as client:
            with pytest.raises(AudioError, match="onbereikbaar"):
                await audio.fetch_playlist(client, PLAYLIST_URL)

    async def test_bytes_that_are_not_there(self):
        server = Server([], [])
        async with server.client() as client:
            with pytest.raises(AudioError, match="404"):
                await audio.fetch_bytes(client, f"{BASE}/init.m4i")


@pytest.mark.asyncio
class TestSegmentAfter:
    async def test_on_the_grid_it_is_one_request(self):
        server = Server(_grid(3), [])
        async with server.client() as client:
            found = await audio.fetch_segment_after(client, BASE, T0 + SEGMENT_TICKS)

        assert found is not None
        segment, data = found
        assert segment.ticks == T0 + SEGMENT_TICKS
        assert segment.url == f"{BASE}/Segment-{T0 + SEGMENT_TICKS}.m4a"
        assert data == f"<{T0 + SEGMENT_TICKS}>".encode()
        assert len(server.requests) == 1

    @pytest.mark.parametrize("nudges", [1, -1, 3, -5, 5])
    async def test_after_a_jump_the_neighbouring_names_are_tried(self, nudges):
        """A segment of 3.88 s moved every later name by 40 ms."""
        there = T0 + SEGMENT_TICKS + nudges * NUDGE_TICKS
        server = Server([there], [])
        async with server.client() as client:
            found = await audio.fetch_segment_after(client, BASE, T0 + SEGMENT_TICKS)

        assert found is not None
        assert found[0].ticks == there

    async def test_the_likeliest_name_is_asked_first(self):
        server = Server([], [])
        async with server.client() as client:
            await audio.fetch_segment_after(client, BASE, T0)

        asked = [int(u.rsplit("-", 1)[1][: -len(".m4a")]) - T0 for u in server.requests]
        assert asked[:5] == [
            0,
            NUDGE_TICKS,
            -NUDGE_TICKS,
            2 * NUDGE_TICKS,
            -2 * NUDGE_TICKS,
        ]
        assert len(asked) == 11

    async def test_too_far_off_is_not_found(self):
        server = Server([T0 + 6 * NUDGE_TICKS], [])
        async with server.client() as client:
            assert await audio.fetch_segment_after(client, BASE, T0) is None

    async def test_a_server_error_is_not_the_end_of_the_audio(self):
        """A 404 means the segment is not there. A 500 means nothing."""
        server = Server(_grid(1), [])
        server.status[f"{BASE}/Segment-{T0}.m4a"] = 500
        async with server.client() as client:
            with pytest.raises(AudioError, match="500"):
                await audio.fetch_segment_after(client, BASE, T0)


@pytest.mark.asyncio
class TestFetchSince:
    async def _since(self, server, after, max_segments=100):
        async with server.client() as client:
            playlist = await audio.fetch_playlist(client, PLAYLIST_URL)
            got = await audio.fetch_since(
                client, playlist, after, max_segments=max_segments
            )
        return [segment.ticks for segment, _ in got], got

    async def test_without_history_it_starts_at_the_playlist(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        ticks, got = await self._since(server, None)

        assert ticks == grid[-5:]
        assert got[0][1] == f"<{grid[-5]}>".encode()

    async def test_only_what_is_new_is_fetched(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, grid[-2])

        assert ticks == grid[-2:]
        assert sum("Segment-" in u for u in server.requests) == 2

    async def test_nothing_new_is_nothing(self):
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, grid[-1] + SEGMENT_TICKS)

        assert ticks == []

    async def test_a_round_that_took_long_misses_nothing(self):
        """The playlist is twenty seconds long. A round of transcribing
        can take longer, and then the playlist has moved on."""
        grid = _grid(20)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, grid[3])

        assert ticks == grid[3:]

    async def test_the_gap_is_closed_across_a_jump(self):
        before = _grid(6)
        after = _grid(10, start=before[-1] + SEGMENT_TICKS + NUDGE_TICKS)
        server = Server([*before, *after], after[-5:])

        ticks, got = await self._since(server, before[2])

        assert ticks == [*before[2:], *after]
        assert len(ticks) == len(set(ticks))

    async def test_two_jumps_in_a_row_do_not_add_up(self):
        """Each next name is looked for from the segment that was found,
        not from where the grid said it would be."""
        first = _grid(4)
        second = _grid(4, start=first[-1] + SEGMENT_TICKS + 3 * NUDGE_TICKS)
        third = _grid(8, start=second[-1] + SEGMENT_TICKS + 3 * NUDGE_TICKS)
        server = Server([*first, *second, *third], third[-5:])

        ticks, _ = await self._since(server, first[0])

        assert ticks == [*first, *second, *third]

    async def test_a_playlist_segment_just_before_the_position_is_not_skipped(self):
        """The length of a segment is known to 40 ms at best. A segment
        that starts that much before where the last one seemed to end is
        the next one, not one that was fetched before."""
        grid = _grid(10)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, grid[5] + NUDGE_TICKS)

        assert ticks == grid[5:]

    async def test_just_before_the_playlist_is_no_reason_to_search(self):
        grid = _grid(10)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, grid[5] - NUDGE_TICKS)

        assert ticks == grid[5:]
        assert sum("Segment-" in u for u in server.requests) == 5

    async def test_no_more_than_asked(self):
        grid = _grid(40)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, grid[0], max_segments=8)

        assert ticks == grid[:8]

    async def test_no_more_than_asked_from_the_playlist_either(self):
        grid = _grid(10)
        server = Server(grid, grid[-5:])

        ticks, _ = await self._since(server, None, max_segments=2)

        assert ticks == grid[-5:-3]

    async def test_audio_the_server_no_longer_has_is_skipped_not_fatal(self, caplog):
        """Away for longer than the server keeps: a hole in the transcript
        is better than a transcript that stops."""
        grid = _grid(40)
        server = Server(grid[30:], grid[-5:])

        with caplog.at_level("WARNING"):
            ticks, _ = await self._since(server, grid[2])

        assert ticks == grid[-5:]
        assert "niet meer op te halen" in caplog.text


def test_joined_audio_starts_with_the_init_section():
    segments = [(Segment(T0, "a"), b"one"), (Segment(T0 + 1, "b"), b"two")]

    assert audio.join_segments(b"init", segments) == b"initonetwo"
