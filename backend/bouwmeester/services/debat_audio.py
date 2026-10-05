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
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

TICKS_PER_SECOND = 10_000_000
# The usual length of a segment, and the size of the jumps away from it.
SEGMENT_TICKS = 38_400_000
NUDGE_TICKS = 400_000
# How many nudges either way are tried to find the segment after a jump.
MAX_NUDGES = 5

_SEGMENT_NAME = re.compile(r"Segment-(\d+)\.m4a")
_HEADERS = {"User-Agent": "Mozilla/5.0"}


class AudioError(RuntimeError):
    """The audio could not be read. Says nothing about the debate."""


def ticks_to_datetime(ticks: int) -> datetime:
    return datetime.fromtimestamp(ticks / TICKS_PER_SECOND, tz=UTC)


def datetime_to_ticks(moment: datetime) -> int:
    return round(moment.timestamp() * TICKS_PER_SECOND)


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
