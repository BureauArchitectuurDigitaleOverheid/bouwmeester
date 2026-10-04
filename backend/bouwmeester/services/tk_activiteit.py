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
from datetime import datetime

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
    # A document can hang directly on the agendapunt or under its zaak;
    # the same one may appear on both routes.
    for doc in [
        *_rows(raw.get("Document")),
        *(d for z in zaken for d in _rows(z.get("Document"))),
    ]:
        nummer = _text(doc.get("DocumentNummer"))
        if not nummer or nummer in seen:
            continue
        seen.add(nummer)
        documenten.append(
            AgendaDocument(
                nummer=nummer,
                soort=_text(doc.get("Soort")) or None,
                onderwerp=_text(doc.get("Onderwerp")) or None,
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
        bewindspersonen=bewindspersonen,
        agendapunten=tuple(agendapunten),
    )


_SELECT = (
    "Id,Nummer,Soort,Onderwerp,Aanvangstijd,Eindtijd,Status,Voortouwnaam,Verwijderd"
)
_EXPAND = (
    "Agendapunt($select=Nummer,Onderwerp,Volgorde,Verwijderd;"
    "$expand=Document($select=DocumentNummer,Soort,Onderwerp,Verwijderd),"
    "Zaak($select=Nummer,Soort,Onderwerp,Verwijderd;"
    "$expand=Document($select=DocumentNummer,Soort,Onderwerp,Verwijderd))),"
    "ActiviteitActor($select=ActorNaam,Relatie,Functie,Verwijderd)"
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
