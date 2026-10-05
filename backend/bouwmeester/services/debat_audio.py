"""Fetch the audio of a debate, segment by segment, each with its own time.

Debat Direct streams the audio of a room as HLS: a playlist that lists the
last five segments of 3.84 seconds. What makes this usable for a transcript
is in the names. A segment is called `Segment-<n>.m4a`, where `n` is its
start time in units of 100 nanoseconds since 1970. So every piece of audio
says exactly when it was spoken, and a segment can be asked for by time.

Measured on a running debate on 5 October 2026:

* The server keeps segments for about fifty minutes after they left the
  playlist. Whoever was away for a while can catch up; after an hour the
  audio is gone for good, and the URL of a room is reused for the next
  debate.
* Segments are not on a fixed grid. Now and then one is 3.88 instead of
  3.84 seconds, and from there on every name is 40 ms off the grid before
  it. Computing the next name blindly then gives a 404 that looks like the
  end of what the server keeps. The neighbouring names have to be tried.
* The stream runs about half a minute behind the room.
* The playlist is on the Kamer's own host, the init section and the
  segments are on a host of the CDN behind it, with their full address.
* A jump of 40 ms comes about once an hour (10 in 7500 segments), so a
  name counted from another one, up to fifty minutes away, is at most a
  few jumps off.

Audio is never kept: `Reach` holds what it fetched for the length of one
round and is thrown away with it. Nothing is written to disk.
"""

from __future__ import annotations

import asyncio
import bisect
import io
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

import httpx
import numpy as np

logger = logging.getLogger(__name__)

TICKS_PER_SECOND = 10_000_000
# The usual length of a segment, and the size of the jumps away from it.
SEGMENT_TICKS = 38_400_000
SEGMENT_SECONDS = SEGMENT_TICKS / TICKS_PER_SECOND
NUDGE_TICKS = 400_000
# How many nudges either way are tried to find the segment after a jump.
MAX_NUDGES = 5

# What the audio is decoded to: what a speaker model listens to.
SAMPLE_RATE = 16_000
# The hosts audio is fetched from. The playlist names a host of the CDN for
# its segments, so "the same host as the playlist" cannot be the rule here
# as it is for the subtitles. A playlist that points anywhere else is not
# followed: the worker would be asking a host of someone else's choosing.
TRUSTED_HOSTS = ("tweedekamer.nl", "vos360.video")

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_TICKS_PER_MICROSECOND = TICKS_PER_SECOND // 1_000_000

_SEGMENT_NAME = re.compile(r"Segment-(\d+)\.m4a")
_HEADERS = {"User-Agent": "Mozilla/5.0"}


class AudioError(RuntimeError):
    """The audio could not be read. Says nothing about the debate."""


def ticks_to_datetime(ticks: int) -> datetime:
    return datetime.fromtimestamp(ticks / TICKS_PER_SECOND, tz=UTC)


def datetime_to_ticks(moment: datetime) -> int:
    # In whole microseconds, not through a float: a float of this size is
    # a few ticks off, and a moment exactly on the edge of a segment then
    # falls on the wrong side of it.
    return ((moment - _EPOCH) // timedelta(microseconds=1)) * _TICKS_PER_MICROSECOND


@dataclass(frozen=True)
class Segment:
    ticks: int
    url: str
    duration: float = SEGMENT_TICKS / TICKS_PER_SECOND

    @property
    def start(self) -> datetime:
        return ticks_to_datetime(self.ticks)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.duration)

    @property
    def end_ticks(self) -> int:
        return self.ticks + round(self.duration * TICKS_PER_SECOND)


@dataclass(frozen=True)
class Playlist:
    init_url: str
    segments: tuple[Segment, ...]

    @property
    def base_url(self) -> str:
        """What a segment name is put behind to ask for it by time."""
        return self.segments[0].url.rsplit("/", 1)[0]


def parse_playlist(text: str) -> Playlist:
    """Read an HLS playlist of a room.

    Raises `AudioError` for anything that is not a playlist with an init
    section and timed segments. That includes the placeholder a room plays
    when nobody is meeting: its segments are not named after a time.
    """
    init = re.search(r'#EXT-X-MAP:URI="([^"]+)"', text)
    if init is None:
        raise AudioError("Afspeellijst zonder init-sectie")
    segments: list[Segment] = []
    duration = SEGMENT_TICKS / TICKS_PER_SECOND
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                duration = float(line[len("#EXTINF:") :].split(",")[0])
            except ValueError:
                duration = SEGMENT_TICKS / TICKS_PER_SECOND
        elif line and not line.startswith("#"):
            name = _SEGMENT_NAME.search(line)
            if name is None:
                raise AudioError("Segment zonder tijd in zijn naam")
            segments.append(Segment(int(name.group(1)), line, duration))
    if not segments:
        raise AudioError("Afspeellijst zonder segmenten")
    return Playlist(init_url=init.group(1), segments=tuple(segments))


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    try:
        return await client.get(url, headers=_HEADERS)
    except httpx.HTTPError as exc:
        raise AudioError(f"Audio onbereikbaar: {url}") from exc


async def fetch_playlist(client: httpx.AsyncClient, url: str) -> Playlist:
    response = await _get(client, url)
    if response.status_code != 200:
        raise AudioError(f"Afspeellijst gaf status {response.status_code}")
    return parse_playlist(response.text)


async def fetch_bytes(client: httpx.AsyncClient, url: str) -> bytes:
    response = await _get(client, url)
    if response.status_code != 200:
        raise AudioError(f"Audio gaf status {response.status_code}: {url}")
    return response.content


def _nudges() -> list[int]:
    """0, +1, -1, +2, -2, ...: the likeliest name first."""
    order = [0]
    for k in range(1, MAX_NUDGES + 1):
        order.extend((k, -k))
    return order


async def fetch_segment_after(
    client: httpx.AsyncClient, base_url: str, after_ticks: int
) -> tuple[Segment, bytes] | None:
    """The segment that starts where the one ending at `after_ticks` stopped.

    Asked for by name. If the name on the grid does not exist, the names a
    few multiples of 40 ms around it are tried: that is what a segment of
    another length leaves behind. ``None`` if none of them exists, which is
    the end of what the server keeps or of what has been broadcast.
    """
    for k in _nudges():
        ticks = after_ticks + k * NUDGE_TICKS
        url = f"{base_url}/Segment-{ticks}.m4a"
        response = await _get(client, url)
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            raise AudioError(f"Audio gaf status {response.status_code}: {url}")
        return Segment(ticks, url), response.content
    return None


async def fetch_since(
    client: httpx.AsyncClient,
    playlist: Playlist,
    after_ticks: int | None,
    *,
    max_segments: int,
) -> list[tuple[Segment, bytes]]:
    """The audio after `after_ticks`, oldest first, at most `max_segments`.

    `after_ticks` is the end of what was fetched before. Without it there
    is no history, and this starts at the playlist: the last twenty seconds.

    With it, the gap between then and the playlist is closed by asking for
    segments by name, so nothing is skipped when a round took longer than
    the playlist is long. If the trail goes cold (the server no longer has
    it), what is missing is skipped with a warning and the playlist is
    picked up again: a hole in the transcript is better than a transcript
    that stops.
    """
    result: list[tuple[Segment, bytes]] = []
    first_listed = playlist.segments[0].ticks
    position = after_ticks

    if position is not None:
        while position < first_listed - NUDGE_TICKS and len(result) < max_segments:
            found = await fetch_segment_after(client, playlist.base_url, position)
            if found is None:
                logger.warning(
                    "Audio tussen %s en %s niet meer op te halen",
                    ticks_to_datetime(position).isoformat(timespec="seconds"),
                    ticks_to_datetime(first_listed).isoformat(timespec="seconds"),
                )
                break
            result.append(found)
            position = found[0].end_ticks

    for segment in playlist.segments:
        if len(result) >= max_segments:
            break
        if position is not None and segment.ticks < position - NUDGE_TICKS:
            continue
        result.append((segment, await fetch_bytes(client, segment.url)))
        position = segment.end_ticks
    return result


def join_segments(init: bytes, segments: list[tuple[Segment, bytes]]) -> bytes:
    """One fragmented mp4 that plays as it is: the init section, then the audio."""
    return init + b"".join(data for _, data in segments)


def is_trusted(url: str) -> bool:
    """Whether an address is https and on a host audio may be fetched from."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and any(
        host == trusted or host.endswith(f".{trusted}") for trusted in TRUSTED_HOSTS
    )


def resolve(playlist: Playlist, playlist_url: str) -> Playlist:
    """The playlist with full addresses, all of them checked.

    Raises `AudioError` when the playlist itself, its init section or one
    of its segments is somewhere audio is not fetched from.
    """
    init_url = urljoin(playlist_url, playlist.init_url)
    segments = tuple(
        Segment(segment.ticks, urljoin(playlist_url, segment.url), segment.duration)
        for segment in playlist.segments
    )
    for url in (playlist_url, init_url, *(segment.url for segment in segments)):
        if not is_trusted(url):
            raise AudioError("Audio op een adres dat niet vertrouwd is")
    return Playlist(init_url=init_url, segments=segments)


def decode(init: bytes, segments: Sequence[bytes]) -> np.ndarray:
    """Fragmented MP4 with AAC to mono samples at 16 kHz, between -1 and 1.

    In this process, from memory to memory. Blocking and not cheap: call it
    through `asyncio.to_thread`.
    """
    # Imported here: without the library the timeline has to keep running,
    # only this step falls away.
    import av

    pieces: list[np.ndarray] = []
    try:
        with av.open(io.BytesIO(init + b"".join(segments)), format="mp4") as container:
            resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    pieces.append(out.to_ndarray()[0])
            for out in resampler.resample(None):
                pieces.append(out.to_ndarray()[0])
    except (av.error.FFmpegError, IndexError, ValueError) as exc:
        # Without the error itself: it can quote the bytes it choked on.
        raise AudioError(f"Audio niet te decoderen ({type(exc).__name__})") from None
    if not pieces:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(pieces).astype(np.float32, copy=False)


class BudgetError(AudioError):
    """This round has fetched as much as a round may."""


class Reach:
    """The audio of a room by time, for the length of one round.

    Segments are asked for by name. The name of the one that holds a given
    moment is counted from a name that is known: one from the playlist, or
    one fetched on an earlier round (`known`, which the caller keeps; it
    holds names, not audio). What is fetched is held until the round is
    over, because the lines around a change of speaker lie in the same few
    segments.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        playlist_url: str,
        known: set[int],
        *,
        max_segments: int,
    ) -> None:
        self.client = client
        self.playlist_url = playlist_url
        self.known = known
        self.left = max_segments
        self._playlist: Playlist | None = None
        self._init: bytes | None = None
        self._fetched: dict[int, tuple[Segment, bytes]] = {}
        # The newest name the server turned out not to have. What it does
        # not have is nearly always what it no longer keeps, so nothing
        # older is asked for in this round: every miss is eleven requests.
        self._gone: int | None = None

    async def _open(self) -> Playlist:
        if self._playlist is None:
            if not is_trusted(self.playlist_url):
                raise AudioError("Audio op een adres dat niet vertrouwd is")
            listed = await fetch_playlist(self.client, self.playlist_url)
            self._playlist = resolve(listed, self.playlist_url)
            self.known.update(segment.ticks for segment in self._playlist.segments)
        return self._playlist

    async def _named(self, ticks: int) -> Segment | None:
        """The segment named `ticks`, or a few times 40 ms beside it."""
        for held in self._fetched.values():
            if abs(held[0].ticks - ticks) <= MAX_NUDGES * NUDGE_TICKS:
                return held[0]
        playlist = await self._open()
        if self._gone is not None and ticks <= self._gone:
            return None
        if self.left < 1:
            raise BudgetError("Genoeg audio voor deze ronde")
        self.left -= 1
        found = await fetch_segment_after(self.client, playlist.base_url, ticks)
        if found is None:
            self._gone = ticks
            return None
        self._fetched[found[0].ticks] = found
        self.known.add(found[0].ticks)
        return found[0]

    async def _holding(self, ticks: int) -> Segment | None:
        """The segment in which the moment `ticks` falls."""
        await self._open()
        names = sorted(self.known)
        at = bisect.bisect_right(names, ticks)
        # The nearest name that is known, on either side.
        near = min(names[max(at - 1, 0) : at + 1], key=lambda name: abs(name - ticks))
        guess = near + ((ticks - near) // SEGMENT_TICKS) * SEGMENT_TICKS
        # Counted over many segments the guess can be a jump off, and then
        # the moment is in the one before or after.
        for _ in range(3):
            segment = await self._named(guess)
            if segment is None:
                return None
            if segment.ticks > ticks:
                guess = segment.ticks - SEGMENT_TICKS
            elif segment.end_ticks <= ticks:
                guess = segment.end_ticks
            else:
                return segment
        return None

    async def has(self, moment: datetime) -> bool:
        """Whether the audio up to this moment has been broadcast.

        The stream runs behind the room. What is not there yet is not
        asked for: that would be eleven requests for a segment that cannot
        exist, and it would look the same as audio that is gone.
        """
        playlist = await self._open()
        return datetime_to_ticks(moment) <= playlist.segments[-1].end_ticks

    async def samples(self, start: datetime, end: datetime) -> np.ndarray | None:
        """What was heard between two moments, as `decode` gives it.

        For a stretch that `has` been broadcast. ``None`` when the server
        does not have all of it any more. Raises `BudgetError` when the
        round has fetched its share: the caller tries again on the next.
        """
        playlist = await self._open()
        first = await self._holding(datetime_to_ticks(start))
        if first is None:
            return None
        run = [first]
        while run[-1].end_ticks < datetime_to_ticks(end):
            following = await self._named(run[-1].end_ticks)
            if following is None:
                return None
            run.append(following)
        if self._init is None:
            self._init = await fetch_bytes(self.client, playlist.init_url)
        heard = await asyncio.to_thread(
            decode, self._init, [self._fetched[segment.ticks][1] for segment in run]
        )
        return cut(heard, run[0].ticks, start, end)


def cut(
    samples: np.ndarray, first_ticks: int, start: datetime, end: datetime
) -> np.ndarray:
    """The samples between two moments, out of audio that begins at a name."""
    begin = (datetime_to_ticks(start) - first_ticks) * SAMPLE_RATE // TICKS_PER_SECOND
    stop = (datetime_to_ticks(end) - first_ticks) * SAMPLE_RATE // TICKS_PER_SECOND
    return samples[max(begin, 0) : max(stop, 0)]
