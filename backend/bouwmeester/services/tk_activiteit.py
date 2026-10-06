"""Read one activiteit (a debate or other meeting) from the TK OData API.

The agenda is known here weeks before the debate: agendapunten with their
zaak and documents, the bewindspersonen, the committee and the times. Debat
Direct carries the same documents but does not know a debate until the day
itself, so for a channel that is set up in advance this is the only source.

Read fresh every time and never from what the convocatie stored. A
convocatie is a snapshot: of 250 measured activiteiten 14 were cancelled
and 11 moved after the convocatie went out.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from bouwmeester.services.kamerstuk_soort import TK_BASE_URL

logger = logging.getLogger(__name__)

STATUS_CANCELLED = "Geannuleerd"
STATUS_MOVED = "Verplaatst"

# An ActiviteitActor with this relation is a member of government who is
# expected at the table. "Afgemeld" is its own relation, so someone who
# cancelled does not show up under this one.
_RELATIE_BEWINDSPERSOON = "Bewindspersoon"


class TkApiError(RuntimeError):
    """The TK API could not be read. Says nothing about the activiteit."""


@dataclass(frozen=True)
class AgendaDocument:
    nummer: str
    soort: str | None
    onderwerp: str | None
    # The zaak this document belongs to. Per document and not per
    # agendapunt: one agendapunt can carry several zaken, and a link built
    # from the zaak of one and the document of another points nowhere.
    zaak_nummer: str | None = None


@dataclass(frozen=True)
class Agendapunt:
    volgorde: int | None
    onderwerp: str
    zaak_nummer: str | None
    documenten: tuple[AgendaDocument, ...]


@dataclass(frozen=True)
class Bewindspersoon:
    naam: str
    functie: str | None


@dataclass(frozen=True)
class Activiteit:
    id: str
    nummer: str | None
    soort: str | None
    onderwerp: str
    aanvang: datetime | None
    einde: datetime | None
    status: str | None
    commissie: str | None
    bewindspersonen: tuple[Bewindspersoon, ...]
    agendapunten: tuple[Agendapunt, ...]
    # A closed meeting is not broadcast.
    besloten: bool = False
    # A meeting that is moved does not keep its id: the old activiteit stays
    # with status "Verplaatst" and a new one, with a new `Id` and a new
    # `Nummer`, takes its place. These two links are the only thing that
    # says they are one debate. Measured on the 1000 convocaties registered
    # from 27 March to 5 October 2026 (one activiteit each): 72 were moved,
    # 66 of those name exactly one successor and 6 none; a successor lists
    # all its predecessors, not only the last one (87 have one, 15 two, 4
    # three, 1 four), and every one of those 133 has status "Verplaatst".
    vervangen_door: tuple[str, ...] = ()
    vervangen_vanuit: tuple[str, ...] = ()


def _parse_moment(value: object) -> datetime | None:
    """Read a timestamp; anything unreadable is ``None``, never a crash."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    # A naive time cannot be compared with "now"; the API always sends an
    # offset, so a value without one is not something to guess about.
    return moment if moment.tzinfo else None


def _text(value: object) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""


def _rows(value: object) -> list[dict]:
    """A list of live objects: no deleted rows, nothing that is not a dict."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict) and not row.get("Verwijderd")]


def _parse_agendapunt(raw: dict) -> Agendapunt:
    zaken = _rows(raw.get("Zaak"))
    documenten: list[AgendaDocument] = []
    seen: set[str] = set()
    # A document can hang directly on the agendapunt or under a zaak; the
    # same one may appear on both routes. The zaak route first, because
    # only there is it known which zaak the document belongs to.
    routes = [
        *(
            (_text(z.get("Nummer")) or None, d)
            for z in zaken
            for d in _rows(z.get("Document"))
        ),
        *((None, d) for d in _rows(raw.get("Document"))),
    ]
    for zaak_nummer, doc in routes:
        nummer = _text(doc.get("DocumentNummer"))
        if not nummer or nummer in seen:
            continue
        seen.add(nummer)
        documenten.append(
            AgendaDocument(
                nummer=nummer,
                soort=_text(doc.get("Soort")) or None,
                onderwerp=_text(doc.get("Onderwerp")) or None,
                zaak_nummer=zaak_nummer,
            )
        )

    volgorde = raw.get("Volgorde")
    onderwerp = _text(raw.get("Onderwerp"))
    if not onderwerp and zaken:
        onderwerp = _text(zaken[0].get("Onderwerp"))
    return Agendapunt(
        # `bool` is an `int` in Python; True is not an order.
        volgorde=volgorde
        if isinstance(volgorde, int) and not isinstance(volgorde, bool)
        else None,
        onderwerp=onderwerp,
        zaak_nummer=(_text(zaken[0].get("Nummer")) or None) if zaken else None,
        documenten=tuple(documenten),
    )


def _linked_ids(value: object) -> tuple[str, ...]:
    """The ids of the activiteiten a link points at, without doubles."""
    ids = (_text(row.get("Id")) for row in _rows(value))
    return tuple(dict.fromkeys(i for i in ids if i))


def parse_activiteit(raw: dict) -> Activiteit:
    """Turn one Activiteit from the API into what the channel needs.

    Tolerant per field: an agenda with one odd agendapunt is still an
    agenda, and a channel without a time is better than no channel.
    """
    agendapunten = [_parse_agendapunt(ap) for ap in _rows(raw.get("Agendapunt"))]
    agendapunten = [ap for ap in agendapunten if ap.onderwerp or ap.documenten]
    # Without an order at the end, and stable among themselves.
    agendapunten.sort(key=lambda ap: (ap.volgorde is None, ap.volgorde or 0))

    bewindspersonen = tuple(
        Bewindspersoon(
            naam=_text(actor.get("ActorNaam")),
            functie=_text(actor.get("Functie")) or None,
        )
        for actor in _rows(raw.get("ActiviteitActor"))
        if _text(actor.get("Relatie")).startswith(_RELATIE_BEWINDSPERSOON)
        and _text(actor.get("ActorNaam"))
    )

    return Activiteit(
        id=_text(raw.get("Id")),
        nummer=_text(raw.get("Nummer")) or None,
        soort=_text(raw.get("Soort")) or None,
        onderwerp=_text(raw.get("Onderwerp")),
        aanvang=_parse_moment(raw.get("Aanvangstijd")),
        einde=_parse_moment(raw.get("Eindtijd")),
        status=_text(raw.get("Status")) or None,
        commissie=_text(raw.get("Voortouwnaam")) or None,
        besloten=raw.get("Besloten") is True,
        bewindspersonen=bewindspersonen,
        agendapunten=tuple(agendapunten),
        vervangen_door=_linked_ids(raw.get("VervangenDoor")),
        vervangen_vanuit=_linked_ids(raw.get("VervangenVanuit")),
    )


_SELECT = (
    "Id,Nummer,Soort,Onderwerp,Aanvangstijd,Eindtijd,Status,"
    "Voortouwnaam,Besloten,Verwijderd"
)
_EXPAND = (
    "Agendapunt($select=Nummer,Onderwerp,Volgorde,Verwijderd;"
    "$expand=Document($select=DocumentNummer,Soort,Onderwerp,Verwijderd),"
    "Zaak($select=Nummer,Soort,Onderwerp,Verwijderd;"
    "$expand=Document($select=DocumentNummer,Soort,Onderwerp,Verwijderd))),"
    "ActiviteitActor($select=ActorNaam,Relatie,Functie,Verwijderd),"
    "VervangenDoor($select=Id,Verwijderd),"
    "VervangenVanuit($select=Id,Verwijderd)"
)


async def fetch_activiteit(
    activiteit_id: str, client: httpx.AsyncClient, base_url: str = TK_BASE_URL
) -> Activiteit | None:
    """Fetch one activiteit with its agenda; ``None`` if it does not exist.

    Raises `TkApiError` if the API cannot be read. That difference matters
    to the caller: "this meeting is gone" is something to tell a human,
    "the API is down" is something to try again.
    """
    try:
        # The id goes into a filter expression. It comes from our own
        # database, but it got there from an API response, and an OData
        # filter is not something to paste unchecked text into.
        guid = str(uuid.UUID(activiteit_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise TkApiError(f"Geen geldig activiteit-id: {activiteit_id!r}") from exc

    params = {
        "$filter": f"Id eq {guid}",
        "$select": _SELECT,
        "$expand": _EXPAND,
    }
    try:
        response = await client.get(f"{base_url}/Activiteit", params=params)
        response.raise_for_status()
        rows = response.json().get("value", [])
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise TkApiError(f"Kon activiteit {guid} niet ophalen") from exc

    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    if rows[0].get("Verwijderd"):
        return None
    return parse_activiteit(rows[0])


# Kinds that are not a meeting anyone can listen to: a deadline for
# written input, a visit somewhere else, a petition handed over in the
# hall, a procedure by e-mail. The API lists them as activiteiten and does
# not mark them as closed.
_SOORT_PREFIX_NO_MEETING = ("Inbreng", "Werkbezoek", "Petitie", "E-mailprocedure")

_PAGE_SIZE = 250  # the API refuses a `$top` above this
_MAX_PAGES = 4

# How far back "upcoming" reaches, so a debate that is running now is still
# in the list. Long ones exist (a wetgevingsoverleg from 11:00 to 23:00);
# what has ended by now is dropped again further on.
_LOOKBACK = timedelta(hours=16)


async def list_upcoming(
    client: httpx.AsyncClient,
    *,
    days: int,
    now: datetime | None = None,
    base_url: str = TK_BASE_URL,
    include_ended: bool = False,
) -> list[Activiteit]:
    """The meetings of the coming days that can be listened to.

    Without their agenda: this is for picking one. Closed meetings, and
    ones that were cancelled or moved, are left out, as are deadlines for
    written input, which the API lists as activiteiten too.

    `include_ended` keeps what started within the lookback and is over by
    its planned end. That end is a plan: a debate runs past it more often
    than not, and only the caller who knows where it really stands can
    tell.

    Raises `TkApiError` if the API cannot be read.
    """
    now = now or datetime.now(UTC)
    start = (now - _LOOKBACK).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "$filter": (
            f"Aanvangstijd ge {start} and Aanvangstijd lt {end} "
            "and Verwijderd eq false and Besloten eq false"
        ),
        "$select": _SELECT,
        # `Id` as a tiebreaker: several meetings start at the same time,
        # and paging over an order with ties may skip or repeat a row.
        "$orderby": "Aanvangstijd asc,Id asc",
        "$top": str(_PAGE_SIZE),
    }
    rows: list[dict] = []
    try:
        for page in range(_MAX_PAGES):
            response = await client.get(
                f"{base_url}/Activiteit",
                params={**params, "$skip": str(page * _PAGE_SIZE)},
            )
            response.raise_for_status()
            batch = response.json().get("value", [])
            if not isinstance(batch, list):
                raise TkApiError("Onverwacht antwoord van de TK-API")
            rows.extend(row for row in batch if isinstance(row, dict))
            if len(batch) < _PAGE_SIZE:
                break
        else:
            logger.warning(
                "Meer dan %d komende vergaderingen; de lijst is afgekapt",
                _MAX_PAGES * _PAGE_SIZE,
            )
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise TkApiError("Kon de komende vergaderingen niet ophalen") from exc

    result = []
    seen: set[str] = set()
    for row in rows:
        activiteit = parse_activiteit(row)
        if not activiteit.id or activiteit.besloten:
            continue
        # A row on two pages would be two list items with one key.
        if activiteit.id in seen:
            continue
        seen.add(activiteit.id)
        # Started within the lookback and already over: nothing to start.
        if (
            not include_ended
            and activiteit.einde is not None
            and activiteit.einde < now
        ):
            continue
        if activiteit.status in (STATUS_CANCELLED, STATUS_MOVED):
            continue
        if (activiteit.soort or "").startswith(_SOORT_PREFIX_NO_MEETING):
            continue
        result.append(activiteit)
    return result
