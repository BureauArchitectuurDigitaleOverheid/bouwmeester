"""Read what is said in a debate from the subtitle track of its stream.

The video stream of a room on Debat Direct carries a Dutch subtitle track:
speech recognition done by the Kamer, one WebVTT file per 3.84 seconds of
stream. That is the text of the debate without running a speech model.

Measured on two running debates on 5 October 2026:

* A file is named after the moment its piece of stream starts, and says so
  again in its `start` parameter. The times inside it count from there, so
  every line has a moment on the clock. Those moments are the moments of
  the sound: a line starts when its first word is spoken.
* A line is in one file only, the one it starts in, also when it runs on
  past the end of that file. Nothing has to be deduplicated.
* A file can be asked for by time for about an hour after it left the
  playlist. One that does not exist gives a 500, not a 404.
* The playlist lists a file about half a minute after its moment.
* It is speech recognition: names and abbreviations come out wrong.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, quote, urljoin, urlsplit

import httpx

logger = logging.getLogger(__name__)

SEGMENT_SECONDS = 3.84
# Segments are now and then 40 ms longer, and every later name moves along.
NUDGE = timedelta(milliseconds=40)
MAX_NUDGES = 5

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_MEDIA = re.compile(r"#EXT-X-MEDIA:(.*)")
_ATTRIBUTE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')
_TIMING = re.compile(
    r"^\s*((?:\d+:)?\d\d:\d\d\.\d{3})\s+-->\s+((?:\d+:)?\d\d:\d\d\.\d{3})"
)
_TAG = re.compile(r"<[^>]*>")


class SubtitleError(RuntimeError):
    """The subtitles could not be read. Says nothing about the debate."""


@dataclass(frozen=True)
class Cue:
    """One line of subtitle, with its moments on the clock."""

    start: datetime
    end: datetime
    text: str


@dataclass(frozen=True)
class Segment:
    start: datetime
    url: str
    duration: float = SEGMENT_SECONDS

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.duration)


def find_subtitle_playlist(master: str, master_url: str) -> str | None:
    """The address of the Dutch subtitle track in the playlist of a stream.

    ``None`` when the stream has no such track, which is for the caller to
    live with: a debate without subtitles still has its timeline.
    """
    fallback: str | None = None
    for line in master.splitlines():
        found = _MEDIA.match(line.strip())
        if found is None:
            continue
        attributes = {
            key: value.strip('"') for key, value in _ATTRIBUTE.findall(found.group(1))
        }
        if attributes.get("TYPE") != "SUBTITLES" or not attributes.get("URI"):
            continue
        url = urljoin(master_url, attributes["URI"])
        if attributes.get("LANGUAGE", "").lower().startswith("nl"):
            return url
        fallback = fallback or url
    return fallback


def _moment(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def parse_playlist(text: str, playlist_url: str) -> list[Segment]:
    """The files a subtitle playlist lists, oldest first.

    The moment of a file is read from its own `start` parameter, not counted
    from the top of the playlist: it is what the file is asked for by.
    """
    segments: list[Segment] = []
    duration = SEGMENT_SECONDS
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                duration = float(line[len("#EXTINF:") :].split(",")[0])
            except ValueError:
                duration = SEGMENT_SECONDS
        elif line and not line.startswith("#"):
            url = urljoin(playlist_url, line)
            start = _moment((parse_qs(urlsplit(url).query).get("start") or [""])[0])
            if start is None:
                raise SubtitleError("Ondertitelbestand zonder tijd")
            segments.append(Segment(start, url, duration))
    if not segments:
        raise SubtitleError("Afspeellijst zonder ondertitels")
    return segments


def _seconds(stamp: str) -> float:
    parts = stamp.split(":")
    seconds = float(parts[-1]) + 60 * int(parts[-2])
    return seconds + (3600 * int(parts[0]) if len(parts) == 3 else 0)


def parse_vtt(text: str, segment_start: datetime) -> list[Cue]:
    """The lines in one WebVTT file, with their moments on the clock.

    A file without lines is normal: nobody spoke. Anything that is not
    WebVTT raises, so an error page is not taken for silence.
    """
    if not text.lstrip("\ufeff").startswith("WEBVTT"):
        raise SubtitleError("Geen WebVTT")
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.strip("\n").split("\n")
        for index, line in enumerate(lines):
            timing = _TIMING.match(line)
            if timing is None:
                continue
            spoken = " ".join(
                _TAG.sub("", part).strip() for part in lines[index + 1 :]
            ).strip()
            spoken = re.sub(r"\s+", " ", spoken)
            if spoken:
                cues.append(
                    Cue(
                        segment_start + timedelta(seconds=_seconds(timing.group(1))),
                        segment_start + timedelta(seconds=_seconds(timing.group(2))),
                        spoken,
                    )
                )
            break
    return cues


def _stamp(moment: datetime) -> str:
    moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def segment_url(playlist_url: str, start: datetime, duration: float) -> str:
    """The address of the file that starts at `start`, to ask for it by time."""
    moment = start.astimezone(UTC)
    name = moment.strftime("%Y%m%d%H%M%S") + f"{moment.microsecond // 1000:03d}"
    end = start + timedelta(seconds=duration)
    return urljoin(
        playlist_url,
        f"live/nl/{name}.vtt?start={quote(_stamp(start))}&end={quote(_stamp(end))}",
    )


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    try:
        return await client.get(url, headers=_HEADERS)
    except httpx.HTTPError as exc:
        raise SubtitleError("Ondertitels onbereikbaar") from exc


async def fetch_text(client: httpx.AsyncClient, url: str) -> str:
    response = await _get(client, url)
    if response.status_code != 200:
        raise SubtitleError(f"Ondertitels gaven status {response.status_code}")
    return response.text


async def fetch_cues(client: httpx.AsyncClient, segment: Segment) -> list[Cue]:
    return parse_vtt(await fetch_text(client, segment.url), segment.start)


async def fetch_segment_at(
    client: httpx.AsyncClient, playlist_url: str, start: datetime
) -> tuple[Segment, list[Cue]] | None:
    """The file that starts at `start`, or a few times 40 ms around it.

    ``None`` if none of those exists: the end of what the server keeps. The
    server answers 500 for a file it does not have, so a real failure of the
    server looks the same and is treated the same.
    """
    order = [0]
    for k in range(1, MAX_NUDGES + 1):
        order.extend((k, -k))
    for k in order:
        moment = start + k * NUDGE
        segment = Segment(moment, segment_url(playlist_url, moment, SEGMENT_SECONDS))
        response = await _get(client, segment.url)
        if response.status_code != 200:
            continue
        return segment, parse_vtt(response.text, moment)
    return None


async def fetch_since(
    client: httpx.AsyncClient,
    playlist_url: str,
    after: datetime | None,
    *,
    max_segments: int,
) -> tuple[list[Cue], datetime | None]:
    """The lines after `after`, oldest first, and where to go on next time.

    `after` is the end of the last file read before. Without it there is no
    history and this starts at the playlist. With it, the stretch between
    then and the playlist is closed by asking for files by time, so a round
    that took long misses nothing. If the trail goes cold the missing
    stretch is skipped with a warning and the playlist is picked up again.

    The second value is the end of the last file read, or `after` itself
    when there was nothing new.
    """
    listed = parse_playlist(await fetch_text(client, playlist_url), playlist_url)
    cues: list[Cue] = []
    position = after
    count = 0

    if position is not None:
        while position < listed[0].start - NUDGE and count < max_segments:
            found = await fetch_segment_at(client, playlist_url, position)
            if found is None:
                logger.warning(
                    "Ondertitels tussen %s en %s niet meer op te halen",
                    position.isoformat(timespec="seconds"),
                    listed[0].start.isoformat(timespec="seconds"),
                )
                break
            cues.extend(found[1])
            position = found[0].end
            count += 1

    for segment in listed:
        if count >= max_segments:
            break
        if position is not None and segment.start < position - NUDGE:
            continue
        cues.extend(await fetch_cues(client, segment))
        position = segment.end
        count += 1
    return cues, position
