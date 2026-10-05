"""Read Debat Direct: which debates there are on a day, and who speaks when.

Debat Direct is the Tweede Kamer's livestream site. Its API is not
documented; what is here was read off its responses and its web app
(October 2026). It can change without notice, so everything is parsed
tolerantly and a debate that cannot be read is skipped, not fatal.

What it gives that the OData API does not: the room, the stream, and
`events`, a list of who got the floor at which moment. That list grows while
a debate runs, a speaker change showing up 5.8 to 8.7 seconds after it
happened (measured on 1 October 2026), and it stays available afterwards.
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from bouwmeester.services.tk_activiteit import Activiteit

logger = logging.getLogger(__name__)

DD_API_URL = "https://cdn.debatdirect.tweedekamer.nl/api"
DD_SITE_URL = "https://debatdirect.tweedekamer.nl"

EVENT_SPEAKER = "speaker"
EVENT_INTERRUPTER = "interrupter"
EVENT_CHAIRMAN = "chairman"
EVENT_CHAIRMAN_CHANGE = "chairman_change"
EVENT_DEBATE_START = "debate_start"
EVENT_DEBATE_END = "debate_end"
EVENT_SUSPENDED = "suspended"
EVENT_CONTINUED = "continued"


class DebatDirectError(RuntimeError):
    """Debat Direct could not be read. Says nothing about the debate."""


@dataclass(frozen=True)
class DdEvent:
    start: datetime
    type: str
    object_id: str
    # The timestamp exactly as the API gave it. A link to this moment is
    # built from this string, and the site matches it literally.
    raw_start: str


@dataclass(frozen=True)
class DdDebat:
    id: str
    name: str
    slug: str
    debate_type: str | None
    debate_date: str | None
    starts_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    location_id: str | None
    location_name: str | None
    category_ids: tuple[str, ...]
    # Oldest first. Empty for a debate read from the agenda: only the
    # detail call carries events.
    events: tuple[DdEvent, ...] = ()


@dataclass(frozen=True)
class Spreker:
    naam: str
    fractie: str | None = None
    titel: str | None = None

    @property
    def label(self) -> str:
        """`Kathmann (GroenLinks-PvdA)`, or the function for a minister.

        The party right behind the name, not in a column of its own.
        """
        if self.fractie:
            return f"{self.naam} ({self.fractie})"
        if self.titel and self.titel != "Tweede Kamerlid":
            return f"{self.naam} ({self.titel})"
        return self.naam


def _moment(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def parse_debate(raw: dict) -> DdDebat | None:
    """One debate from the agenda or the detail call; ``None`` without an id."""
    debate_id = _text(raw.get("id"))
    if not debate_id:
        return None
    events: list[DdEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw.get("events") or []:
        if not isinstance(item, dict):
            continue
        raw_start = item.get("eventStart")
        start = _moment(raw_start)
        kind = _text(item.get("eventType"))
        if start is None or not kind:
            continue
        object_id = _text(item.get("objectId"))
        key = (raw_start, kind, object_id)
        if key in seen:
            continue
        seen.add(key)
        events.append(DdEvent(start, kind, object_id, raw_start))
    # The API returns newest first. Order by time and, within one second,
    # keep the order of things happening: a debate starts before someone
    # speaks in it.
    rank = {EVENT_DEBATE_START: 0, EVENT_CONTINUED: 0, EVENT_DEBATE_END: 9}
    events.sort(key=lambda e: (e.start, rank.get(e.type, 5)))

    categories = raw.get("categoryIds")
    return DdDebat(
        id=debate_id,
        name=_text(raw.get("name")),
        slug=_text(raw.get("slug")),
        debate_type=_text(raw.get("debateType")) or None,
        debate_date=_text(raw.get("debateDate")) or None,
        starts_at=_moment(raw.get("startsAt")),
        started_at=_moment(raw.get("startedAt")),
        ended_at=_moment(raw.get("endedAt")),
        location_id=_text(raw.get("locationId")) or None,
        location_name=_text(raw.get("locationName")) or None,
        category_ids=tuple(
            c for c in (categories if isinstance(categories, list) else []) if c
        ),
        events=tuple(events),
    )


async def _get(client: httpx.AsyncClient, path: str, base_url: str) -> httpx.Response:
    try:
        return await client.get(
            f"{base_url}/{path}",
            # Without a browser-like agent the CDN answers 403.
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise DebatDirectError(f"Debat Direct onbereikbaar ({path})") from exc


async def fetch_agenda(
    client: httpx.AsyncClient, day: date, base_url: str = DD_API_URL
) -> list[DdDebat]:
    """The debates Debat Direct knows for this day."""
    response = await _get(client, f"agenda/{day.isoformat()}", base_url)
    try:
        response.raise_for_status()
        rows = response.json().get("debates", [])
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise DebatDirectError(f"Agenda van {day} niet te lezen") from exc
    if not isinstance(rows, list):
        raise DebatDirectError(f"Agenda van {day} heeft een onverwachte vorm")
    debates = [parse_debate(row) for row in rows if isinstance(row, dict)]
    return [d for d in debates if d is not None]


async def fetch_debate(
    client: httpx.AsyncClient, debate_id: str, base_url: str = DD_API_URL
) -> DdDebat | None:
    """One debate with its events; ``None`` if Debat Direct does not know it."""
    response = await _get(client, f"debates/{quote(debate_id, safe='')}", base_url)
    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
        raw = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DebatDirectError(f"Debat {debate_id} niet te lezen") from exc
    if not isinstance(raw, dict):
        raise DebatDirectError(f"Debat {debate_id} heeft een onverwachte vorm")
    return parse_debate(raw)


async def fetch_sprekers(
    client: httpx.AsyncClient, day: date, base_url: str = DD_API_URL
) -> dict[str, Spreker]:
    """Everyone who can speak on this day, by the id the events carry.

    Members of parliament with their party, members of government with
    their function. This is what spares the speech recognition from telling
    speakers apart: the name comes from here, as a fact.
    """
    response = await _get(client, f"actors/{day.isoformat()}", base_url)
    try:
        response.raise_for_status()
        raw = response.json()
        politicians = raw.get("politicians") or []
        parties = raw.get("parties") or []
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise DebatDirectError(f"Sprekers van {day} niet te lezen") from exc

    fracties = {
        str(p.get("id")).lower(): _text(p.get("shorthand")) or _text(p.get("name"))
        for p in parties
        if isinstance(p, dict) and p.get("id")
    }
    sprekers: dict[str, Spreker] = {}
    for p in politicians:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        naam = _text(p.get("name")) or " ".join(
            x for x in (_text(p.get("firstName")), _text(p.get("lastName"))) if x
        )
        if not naam:
            continue
        sprekers[str(p["id"])] = Spreker(
            naam=naam,
            # Party ids differ in case between the two lists.
            fractie=fracties.get(str(p.get("partyId") or "").lower()) or None,
            titel=_text(p.get("title")) or None,
        )
    return sprekers


def debate_url(debat: DdDebat) -> str | None:
    """The page of this debate on Debat Direct, where the stream plays."""
    if not (debat.debate_date and debat.location_id and debat.slug):
        return None
    category = debat.category_ids[0] if debat.category_ids else "overig"
    return "/".join(
        [
            DD_SITE_URL,
            quote(debat.debate_date, safe=""),
            quote(category, safe=""),
            quote(debat.location_id, safe=""),
            quote(debat.slug, safe=""),
        ]
    )


def moment_url(debat: DdDebat, event: DdEvent) -> str | None:
    """A link that opens the broadcast at this event.

    The site reads `?event=<type><timestamp>` and seeks to it; that is how
    its own "spreekmomenten" link. The timestamp has to be the string the
    API gave, offset and all.
    """
    base = debate_url(debat)
    if base is None:
        return None
    return f"{base}?event={quote(f'{event.type}{event.raw_start}', safe='')}"


def _norm(tekst: str) -> str:
    plat = unicodedata.normalize("NFKD", tekst or "")
    plat = "".join(c for c in plat if not unicodedata.combining(c)).lower()
    plat = re.sub(r"\(.*?\)", " ", plat)
    plat = re.sub(r"\btweeminutendebat\b", " ", plat)
    plat = re.sub(r"[^a-z0-9 ]", " ", plat)
    return re.sub(r"\s+", " ", plat).strip()


def similarity(a: str, b: str) -> float:
    """How alike two subjects are, 0 to 1.

    Debat Direct often carries a shortened version of the OData subject, so
    one containing the other counts as nearly equal.
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    score = difflib.SequenceMatcher(None, na, nb).ratio()
    if na in nb or nb in na:
        score = max(score, 0.92)
    return score


# The thresholds the measurement used: over four days, 46 of 48 listenable
# debates matched on these and none was ambiguous.
_MIN_SIMILARITY = 0.80
_MAX_START_DIFFERENCE = timedelta(minutes=90)


def _type_fits(activiteit_soort: str | None, debate_type: str | None) -> bool:
    """Same kind of meeting, as far as both sides say.

    OData says "Plenair debat (wetgeving)" where Debat Direct says "Plenair
    debat"; the part before the bracket is what they share. Without a kind
    on either side there is nothing to hold against the match.
    """
    if not activiteit_soort or not debate_type:
        return True
    a = _norm(activiteit_soort)
    b = _norm(debate_type)
    return a == b or a.startswith(b) or b.startswith(a)


def match_debates(activiteit: Activiteit, debates: list[DdDebat]) -> list[DdDebat]:
    """The Debat Direct debates that are this activiteit, oldest first.

    There is no shared key, so this goes on subject, kind and start time.
    More than one is possible and correct: Debat Direct cuts a plenary
    debate in two around a break, against one activiteit.

    The start time only counts for the first part. A second part starts
    hours after the activiteit does, and is recognised by carrying the same
    subject as a part that did match on time.
    """
    alike = [
        debat
        for debat in debates
        if similarity(activiteit.onderwerp, debat.name) >= _MIN_SIMILARITY
        and _type_fits(activiteit.soort, debat.debate_type)
    ]
    if not alike:
        return []

    def start_of(debat: DdDebat) -> datetime | None:
        return debat.started_at or debat.starts_at

    if activiteit.aanvang is not None:
        on_time = [
            debat
            for debat in alike
            if (start := start_of(debat)) is not None
            and abs(start - activiteit.aanvang) <= _MAX_START_DIFFERENCE
        ]
        if not on_time:
            return []
        # Later parts: same subject, starting after the part that matched.
        first = min(start_of(d) for d in on_time)  # type: ignore[type-var]
        alike = [
            debat
            for debat in alike
            if (start := start_of(debat)) is not None and start >= first
        ]

    def order(debat: DdDebat) -> tuple[bool, float]:
        start = start_of(debat)
        return (start is None, start.timestamp() if start else 0.0)

    return sorted(alike, key=order)
