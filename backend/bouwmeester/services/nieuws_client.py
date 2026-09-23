"""Leest RSS-feeds van vakmedia die over de digitale overheid schrijven.

Waarom dit anders werkt dan `TkconvClient`, en waarom dat het ontwerp
bepaalt: tkconv doorzoekt de volledige tekst van kamerstukken aan de
serverkant, dus we sturen een zoekterm en krijgen de stukken terug waarin
die term ergens staat, bijlagen incluis. Een nieuws-RSS kent geen
zoekparameter. Je krijgt de laatste N artikelen en verder niets.

Gemeten op 23 september 2026:

| Feed                              | Items | Teaser | Volledige tekst |
|-----------------------------------|-------|--------|-----------------|
| binnenlandsbestuur.nl/feeds/...   | 150   | 345    | nee             |
| ibestuur.nl/feeds/articles.rss    | 150   | 131    | nee             |

Geen van beide draagt `content:encoded`, dus we zoeken in titel plus
teaser. Dat is een bewuste beperking: een artikel dat het onderwerp pas in
alinea vier noemt, vinden we niet. Voor nieuws is dat minder erg dan voor
kamerstukken, want een artikel gaat meestal over zijn kop, en het
alternatief (elke artikelpagina ophalen) zou 150 verzoeken per ronde
betekenen op een site die daar niet om gevraagd heeft.

De feeds staan los van de zoekopdracht, dus we halen ze één keer op en
matchen alle abonnementen ertegen. Eén verzoek per bron per ronde.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "bouwmeester-signalen/1.0 "
    "(+https://github.com/BureauArchitectuurDigitaleOverheid; "
    "monitort publicaties over de digitale overheid)"
)

TIMEOUT = 20.0

# Een feed van 150 items met teasers is ongeveer 170 kB. Ruim daarboven
# gaan zitten vangt een bron die ineens volledige artikelen meestuurt,
# zonder een geheugenprobleem te worden.
MAX_FEED_BYTES = 8 * 1024 * 1024

_TAG = re.compile(r"<[^>]+>")
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_WS = re.compile(r"\s+")


@dataclass
class NieuwsItem:
    """Eén artikel uit een feed, al ontdaan van opmaak."""

    gid: str
    titel: str
    samenvatting: str
    link: str
    gepubliceerd: datetime | None
    bron: str

    @property
    def doorzoekbare_tekst(self) -> str:
        """Waar een zoekterm in gevonden mag worden.

        Titel en teaser samen. Zie de moduledocstring: de feeds dragen
        geen volledige tekst, dus dit is alles wat er is.
        """
        return f"{self.titel}\n{self.samenvatting}"


def _schoon(ruwe: str | None) -> str:
    """Haal CDATA, tags en dubbele witruimte weg."""
    if not ruwe:
        return ""
    tekst = _CDATA.sub(r"\1", ruwe)
    tekst = _TAG.sub(" ", tekst)
    tekst = (
        tekst.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .replace("&nbsp;", " ")
    )
    return _WS.sub(" ", tekst).strip()


def _veld(blok: str, naam: str) -> str:
    m = re.search(rf"<{naam}[^>]*>(.*?)</{naam}>", blok, re.S)
    return _schoon(m.group(1)) if m else ""


def _datum(ruwe: str) -> datetime | None:
    """RSS gebruikt RFC 822, Atom gebruikt ISO 8601."""
    if not ruwe:
        return None
    try:
        return parsedate_to_datetime(ruwe)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(ruwe.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_feed(xml: str, bron: str) -> list[NieuwsItem]:
    """Haal de items uit een RSS- of Atom-feed.

    Met de hand in plaats van met feedparser: het formaat is hier klein en
    voorspelbaar, en een afhankelijkheid erbij voor twee reguliere
    expressies is het niet waard. Valt een veld weg, dan slaan we het item
    over in plaats van een lege alert te maken.
    """
    items: list[NieuwsItem] = []
    blokken = re.findall(r"<item>(.*?)</item>", xml, re.S)
    atom = False
    if not blokken:
        blokken = re.findall(r"<entry[^>]*>(.*?)</entry>", xml, re.S)
        atom = True

    for blok in blokken:
        titel = _veld(blok, "title")
        if not titel:
            continue

        if atom:
            m = re.search(r'<link[^>]*href="([^"]+)"', blok)
            link = m.group(1) if m else ""
            samenvatting = _veld(blok, "summary") or _veld(blok, "content")
            datum = _datum(_veld(blok, "updated") or _veld(blok, "published"))
        else:
            link = _veld(blok, "link")
            samenvatting = _veld(blok, "description")
            datum = _datum(_veld(blok, "pubDate"))

        # De guid is de stabiele sleutel; niet elke feed heeft er een, en
        # dan is de link het beste alternatief.
        gid = _veld(blok, "guid") or link
        if not gid:
            continue

        items.append(
            NieuwsItem(
                gid=gid,
                titel=titel,
                samenvatting=samenvatting,
                link=link,
                gepubliceerd=datum,
                bron=bron,
            )
        )
    return items


class NieuwsClient:
    """Haalt feeds op, met conditional GET zodat een ronde niets kost.

    De ETags staan op moduleniveau bij de aanroeper (zie
    `NieuwsStrategy`), omdat de import-service elke ronde een verse client
    bouwt. Op de instantie zou de cache nooit raak zijn.
    """

    def __init__(self, etags: dict[str, str] | None = None) -> None:
        self._client: httpx.AsyncClient | None = None
        self._etags = etags if etags is not None else {}

    async def __aenter__(self) -> "NieuwsClient":
        self._client = httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def haal(self, url: str, bron: str) -> list[NieuwsItem]:
        """Eén feed. Een fout is geen uitzondering maar een lege lijst.

        Een bron die plat ligt mag de ronde van de andere bronnen niet
        meenemen, en al helemaal niet die van de kamerstukken.
        """
        if self._client is None:
            logger.error("NieuwsClient gebruikt buiten zijn context")
            return []

        headers = {}
        etag = self._etags.get(url)
        if etag:
            headers["If-None-Match"] = etag

        try:
            resp = await self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Feed %s onbereikbaar: %s", url, exc)
            return []

        if resp.status_code == 304:
            logger.debug("Feed %s ongewijzigd (304)", url)
            return []

        if resp.status_code != 200:
            logger.warning("Feed %s gaf status %d", url, resp.status_code)
            return []

        if len(resp.content) > MAX_FEED_BYTES:
            logger.warning(
                "Feed %s is %d bytes, boven de limiet", url, len(resp.content)
            )
            return []

        nieuwe_etag = resp.headers.get("ETag")
        if nieuwe_etag:
            self._etags[url] = nieuwe_etag

        return parse_feed(resp.text, bron)
