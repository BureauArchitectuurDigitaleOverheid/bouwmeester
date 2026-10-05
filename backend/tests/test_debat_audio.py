"""Tests for fetching the audio of a debate, segment by segment.

The server is a fake that knows which segments exist, the way the real one
does: the playlist lists the last five, older ones are there by name for a
while, and anything else is a 404.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import av
import httpx
import numpy as np
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
        # The init section, for a server that has one.
        self.init: bytes | None = None

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
        if name == "init.m4i" and self.init is not None:
            return httpx.Response(200, content=self.init)
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


class TestTrust:
    @pytest.mark.parametrize(
        "url",
        [
            "https://livestreaming.tweedekamer.nl/live/zaal/audio/prog_index.m3u8",
            "https://tweedekamer.nl/a.m4a",
            "https://cdn-01.vos360.video/Content/Segment-1.m4a",
        ],
    )
    def test_the_kamer_and_its_cdn_are_fetched_from(self, url):
        assert audio.is_trusted(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://livestreaming.tweedekamer.nl/a.m4a",
            "https://tweedekamer.nl.evil.example/a.m4a",
            "https://nottweedekamer.nl/a.m4a",
            "https://169.254.169.254/latest/meta-data",
            "https://localhost/a.m4a",
            "file:///etc/passwd",
            "",
        ],
    )
    def test_anything_else_is_not(self, url):
        assert not audio.is_trusted(url)

    def test_a_playlist_gets_full_addresses(self):
        listed = audio.Playlist("init.m4i", (Segment(T0, f"Segment-{T0}.m4a", 3.88),))

        resolved = audio.resolve(listed, "https://a.tweedekamer.nl/zaal/p.m3u8")

        assert resolved.init_url == "https://a.tweedekamer.nl/zaal/init.m4i"
        assert resolved.segments == (
            Segment(T0, f"https://a.tweedekamer.nl/zaal/Segment-{T0}.m4a", 3.88),
        )

    @pytest.mark.parametrize(
        ("playlist_url", "init", "segment"),
        [
            ("https://evil.example/p.m3u8", "init.m4i", "Segment-1.m4a"),
            ("https://a.tweedekamer.nl/p.m3u8", "https://evil.example/i", "s.m4a"),
            ("https://a.tweedekamer.nl/p.m3u8", "i", "https://evil.example/s"),
            ("https://a.tweedekamer.nl/p.m3u8", "i", "http://a.tweedekamer.nl/s"),
        ],
    )
    def test_a_playlist_that_points_elsewhere_is_refused(
        self, playlist_url, init, segment
    ):
        listed = audio.Playlist(init, (Segment(T0, "ok.m4a"), Segment(T0, segment)))

        with pytest.raises(AudioError, match="vertrouwd"):
            audio.resolve(listed, playlist_url)


def _tone(seconds: float, hertz: float, rate: int = 48_000) -> bytes:
    """A sine as fragmented MP4 with AAC: what the stream is made of."""
    buffer = io.BytesIO()
    with av.open(
        buffer,
        "w",
        format="mp4",
        options={"movflags": "frag_keyframe+empty_moov+default_base_moof"},
    ) as container:
        stream = container.add_stream("aac", rate=rate, layout="stereo")
        moments = np.arange(int(seconds * rate)) / rate
        wave = (0.5 * np.sin(2 * np.pi * hertz * moments)).astype(np.float32)
        for at in range(0, len(wave), 1024):
            piece = wave[at : at + 1024]
            frame = av.AudioFrame.from_ndarray(
                np.stack([piece, piece]), format="fltp", layout="stereo"
            )
            frame.sample_rate = rate
            frame.pts = at
            container.mux(stream.encode(frame))
        container.mux(stream.encode(None))
    return buffer.getvalue()


class TestDecode:
    def test_aac_becomes_mono_samples_at_16_khz(self):
        encoded = _tone(2.0, 440.0)
        # Cut where the stream is cut: the init section, then the audio.
        split = encoded.index(b"moof") - 4

        heard = audio.decode(encoded[:split], [encoded[split:]])

        assert heard.dtype == np.float32
        assert heard.ndim == 1
        assert abs(len(heard) - 2.0 * audio.SAMPLE_RATE) < 0.1 * audio.SAMPLE_RATE
        assert 0.3 < float(np.abs(heard).max()) <= 1.0
        # Still the same tone: the strongest frequency is the one put in.
        spectrum = np.abs(np.fft.rfft(heard[4000:20000]))
        loudest = np.fft.rfftfreq(16000, 1 / audio.SAMPLE_RATE)[spectrum.argmax()]
        assert abs(loudest - 440.0) < 5

    def test_what_is_not_audio_is_an_audio_error(self):
        with pytest.raises(AudioError, match="decoderen") as raised:
            audio.decode(b"not an init section", [b"not audio either"])

        # Not the bytes it choked on, and not the error that quotes them.
        assert "not audio" not in str(raised.value)
        assert raised.value.__cause__ is None

    def test_nothing_in_nothing_out(self):
        encoded = _tone(1.0, 440.0)
        split = encoded.index(b"moof") - 4

        heard = audio.decode(encoded[:split], [])

        assert len(heard) == 0


class TestCut:
    def test_the_samples_between_two_moments(self):
        samples = np.arange(10 * audio.SAMPLE_RATE, dtype=np.float32)
        start = audio.ticks_to_datetime(T0)

        piece = audio.cut(
            samples, T0, start + timedelta(seconds=2), start + timedelta(seconds=3.5)
        )

        assert piece[0] == 2 * audio.SAMPLE_RATE
        assert len(piece) == 1.5 * audio.SAMPLE_RATE

    def test_a_moment_before_the_audio_starts_at_its_beginning(self):
        samples = np.arange(audio.SAMPLE_RATE, dtype=np.float32)
        start = audio.ticks_to_datetime(T0)

        piece = audio.cut(
            samples, T0, start - timedelta(seconds=1), start + timedelta(seconds=0.5)
        )

        assert piece[0] == 0
        assert len(piece) == 0.5 * audio.SAMPLE_RATE

    def test_all_of_it_before_the_audio_is_nothing(self):
        samples = np.arange(audio.SAMPLE_RATE, dtype=np.float32)
        start = audio.ticks_to_datetime(T0)

        piece = audio.cut(
            samples, T0, start - timedelta(seconds=3), start - timedelta(seconds=1)
        )

        assert len(piece) == 0


def _moment(ticks: int, seconds: float = 0.0) -> datetime:
    return audio.ticks_to_datetime(ticks) + timedelta(seconds=seconds)


def _server(existing: list[int], listed: list[int]) -> Server:
    server = Server(existing, listed)
    server.init = b"<init>"
    return server


@pytest.mark.asyncio
class TestReach:
    """Audio by time. The decoder is a fake that gives back which segments
    it was handed, so a test sees what was fetched for a stretch of time."""

    @pytest.fixture(autouse=True)
    def _fakes(self, monkeypatch):
        monkeypatch.setattr(audio, "TRUSTED_HOSTS", ("stream.example",))

        def decode(init, segments):
            self.decoded.append((init, list(segments)))
            # Each sample its own number, counted from the first segment.
            return np.arange(
                len(segments) * round(audio.SEGMENT_SECONDS * audio.SAMPLE_RATE),
                dtype=np.float32,
            )

        self.decoded: list[tuple[bytes, list[bytes]]] = []
        monkeypatch.setattr(audio, "decode", decode)

    async def _samples(self, server, start, end, *, known=None, max_segments=20):
        known = set() if known is None else known
        async with server.client() as client:
            reach = audio.Reach(client, PLAYLIST_URL, known, max_segments=max_segments)
            return await reach.samples(start, end), reach

    def _fetched(self) -> list[bytes]:
        return self.decoded[-1][1]

    async def test_a_stretch_inside_one_listed_segment(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])

        heard, _ = await self._samples(
            server, _moment(grid[6], 1.0), _moment(grid[6], 3.0)
        )

        assert self._fetched() == [f"<{grid[6]}>".encode()]
        assert len(heard) == 2 * audio.SAMPLE_RATE
        assert heard[0] == 1 * audio.SAMPLE_RATE
        assert self.decoded[-1][0] == b"<init>"

    async def test_a_stretch_over_three_segments(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])

        heard, _ = await self._samples(
            server, _moment(grid[6], 3.0), _moment(grid[8], 1.0)
        )

        assert self._fetched() == [f"<{g}>".encode() for g in grid[6:9]]
        assert len(heard) == round((2 * 3.84 - 2.0) * audio.SAMPLE_RATE)

    async def test_a_stretch_that_ends_where_a_segment_ends_needs_no_next_one(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])

        await self._samples(server, _moment(grid[6]), _moment(grid[7]))

        assert self._fetched() == [f"<{grid[6]}>".encode()]

    async def test_long_ago_is_asked_for_by_name(self):
        """Counted back from the playlist: 300 segments is twenty minutes."""
        grid = _grid(400)
        server = _server(grid, grid[-5:])

        await self._samples(server, _moment(grid[95], 0.5), _moment(grid[95], 2.0))

        assert self._fetched() == [f"<{grid[95]}>".encode()]
        # The playlist, the segment, the init section. No searching.
        assert len(server.requests) == 3

    async def test_a_jump_between_then_and_now_is_stepped_over(self):
        """One segment of 3.88 s: every name before it is 40 ms off the
        grid counted back from the playlist."""
        late = _grid(10, T0 + 50 * SEGMENT_TICKS + NUDGE_TICKS)
        early = _grid(50)
        server = _server(early + late, late[-5:])

        await self._samples(server, _moment(early[20], 1.0), _moment(early[20], 2.0))

        assert self._fetched() == [f"<{early[20]}>".encode()]

    async def test_a_moment_at_the_very_start_of_a_segment_after_a_jump(self):
        """Counted back over the jump, the name lands in the segment
        before: what is found ends before the moment, and the next is it."""
        late = _grid(10, T0 + 50 * SEGMENT_TICKS + NUDGE_TICKS)
        early = _grid(50)
        server = _server(early + late, late[-5:])

        await self._samples(server, _moment(early[20], 0.01), _moment(early[20], 1.0))

        assert self._fetched() == [f"<{early[20]}>".encode()]

    async def test_a_moment_at_the_very_end_of_a_segment_before_a_jump(self):
        """Counted forward over the jump, the other way round: what is
        found begins after the moment, and the one before it is it."""
        early = _grid(50)
        late = _grid(10, T0 + 50 * SEGMENT_TICKS + NUDGE_TICKS)
        server = _server(early + late, early[:5])

        await self._samples(server, _moment(late[3], 3.83), _moment(late[3], 3.84))

        assert self._fetched() == [f"<{late[3]}>".encode()]

    async def test_a_name_fetched_before_is_counted_from(self):
        grid = _grid(400)
        server = _server(grid, grid[-5:])
        known: set[int] = set()
        await self._samples(
            server, _moment(grid[95], 0.5), _moment(grid[95], 2.0), known=known
        )

        assert grid[95] in known
        assert set(grid[-5:]) <= known

    async def test_what_the_server_no_longer_has_is_none(self):
        grid = _grid(400)
        server = _server(grid[100:], grid[-5:])

        heard, _ = await self._samples(
            server, _moment(grid[50], 0.5), _moment(grid[50], 2.0)
        )

        assert heard is None
        assert not self.decoded

    async def test_what_has_not_been_broadcast_yet_is_none(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])

        async with server.client() as client:
            reach = audio.Reach(client, PLAYLIST_URL, set(), max_segments=5)

            assert await reach.has(_moment(grid[9], 3.84))
            assert not await reach.has(_moment(grid[9], 3.85))

        # Known from the playlist alone.
        assert server.requests == [PLAYLIST_URL]

    async def test_after_a_miss_nothing_older_is_asked_for_in_the_same_round(self):
        """A segment the server does not have is eleven requests. What
        is older than one that is gone is gone too."""
        grid = _grid(400)
        server = _server(grid[100:], grid[-5:])
        async with server.client() as client:
            reach = audio.Reach(client, PLAYLIST_URL, set(), max_segments=20)
            assert await reach.samples(_moment(grid[50]), _moment(grid[50], 1)) is None
            asked = len(server.requests)
            assert await reach.samples(_moment(grid[40]), _moment(grid[40], 1)) is None
            assert await reach.samples(_moment(grid[50]), _moment(grid[50], 1)) is None

            assert len(server.requests) == asked == 1 + 2 * audio.MAX_NUDGES + 1
            # What is newer is still asked for.
            assert (
                await reach.samples(_moment(grid[200]), _moment(grid[200], 1))
                is not None
            )

    async def test_a_segment_is_fetched_once_in_a_round(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])
        async with server.client() as client:
            reach = audio.Reach(client, PLAYLIST_URL, set(), max_segments=20)
            await reach.samples(_moment(grid[6], 0.5), _moment(grid[6], 1.5))
            await reach.samples(_moment(grid[6], 2.0), _moment(grid[7], 1.0))

        named = [r for r in server.requests if "Segment-" in r]
        assert len(named) == len(set(named)) == 2
        # And the playlist and the init section once each.
        assert len(server.requests) == 4

    async def test_no_more_segments_than_the_round_may_fetch(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])

        async with server.client() as client:
            reach = audio.Reach(client, PLAYLIST_URL, set(), max_segments=2)
            with pytest.raises(audio.BudgetError):
                await reach.samples(_moment(grid[2], 0.5), _moment(grid[5], 1.0))

            assert reach.left == 0
            assert len([r for r in server.requests if "Segment-" in r]) == 2

    async def test_a_playlist_somewhere_else_is_not_fetched(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])
        async with server.client() as client:
            reach = audio.Reach(
                client, "https://evil.example/prog_index.m3u8", set(), max_segments=5
            )
            with pytest.raises(AudioError, match="vertrouwd"):
                await reach.samples(_moment(grid[6]), _moment(grid[6], 1.0))

        assert server.requests == []

    async def test_segments_somewhere_else_are_not_fetched(self, monkeypatch):
        grid = _grid(10)
        server = _server(grid, grid[-5:])
        monkeypatch.setattr(audio, "is_trusted", lambda url: "prog_index" in url)

        with pytest.raises(AudioError, match="vertrouwd"):
            await self._samples(server, _moment(grid[6]), _moment(grid[6], 1.0))

        assert server.requests == [PLAYLIST_URL]

    async def test_a_server_that_is_down_is_an_audio_error(self):
        grid = _grid(10)
        server = _server(grid, grid[-5:])
        server.unreachable = True

        with pytest.raises(AudioError):
            await self._samples(server, _moment(grid[6]), _moment(grid[6], 1.0))


@pytest.mark.asyncio
async def test_a_request_for_audio_does_not_wait_as_long_as_the_client_would():
    """The timeline waits for every request. A server that hangs is given
    up on in seconds, whatever the client was made with."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, content=b"x")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, timeout=15.0) as client:
        await audio.fetch_bytes(client, "https://stream.example/init.m4i")

    assert set(seen[0].values()) == {audio.REQUEST_TIMEOUT}
    assert audio.REQUEST_TIMEOUT <= 5
