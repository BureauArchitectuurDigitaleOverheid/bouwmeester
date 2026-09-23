"""Client voor de zoek-RSS van tkconv (berthub.eu/tkconv).

Waarom naast `tk_api_client`, die al bij de Tweede Kamer ophaalt: de
officiele OData-API doorzoekt alleen metadata (Titel, Onderwerp), tkconv
doorzoekt de volledige tekst van documenten inclusief bijlagen en
beslisnota's. Een meting op 22 september 2026 over de termen "Nederlandse
Digitale Dienst" en "Regelrecht" gaf nul overlap met wat de zaak-API
oplevert:

- 2026D45065 ("Startnotitie Nederlandse Digitale Dienst") is een Bijlage
  zonder Zaak-koppeling, alleen bereikbaar via BronDocument. Zaak-gebaseerd
  importeren ziet die nooit.
- 2026D45064 heet "Strategische inzet digitalisering". Noch de titel noch
  het onderwerp noemt de term; die staat pas in de body. Geen enkele
  metadata-query vindt dit stuk.

De zoek-RSS is niet gedocumenteerd. Behandel hem navenant: identificeer
jezelf in de User-Agent, poll rustig, en faal zacht als het formaat wijzigt.
"""

import asyncio
import logging
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from bouwmeester.services.document_extract import extract_text

logger = logging.getLogger(__name__)

BASE_URL = "https://berthub.eu/tkconv"

# tkconv draait op een privéserver zonder SLA. Een herkenbare UA laat de
# beheerder zien wie er langskomt en hoe hij ons bereikt als het endpoint
# wijzigt.
USER_AGENT = (
    "bouwmeester-parlementaire-alerts/1.0 "
    "(+https://github.com/MinBZK; Nederlandse Digitale Dienst)"
)

# Hoe lang we op één document wachten. De PDF's zijn klein (~100KB), maar
# de server is van één persoon; geef hem de tijd in plaats van te retryen.
DOCUMENT_TIMEOUT = 60.0
SEARCH_TIMEOUT = 30.0

# Hoeveel tekst we van een document bewaren. De standaard van
# `document_extract` is 15.000 tekens, en dat bleek te weinig: de memorie
# van toelichting bij de EZ-begroting is 409.830 tekens en noemt de
# Nederlandse Digitale Dienst pas op positie 44.954. Het model kreeg
# daardoor alleen de voorpagina met begrotingsstaten te zien en gaf een
# relevantiescore van 8 aan een stuk dat beschrijft wat de dienst gaat
# doen. `zoekterm_passage` knipt hierna rond de vindplaats, dus dit is
# opslag en geen promptruimte.
MAX_DOCUMENT_TEKENS = 500_000

# Hoeveel bytes we van één document binnenhalen voordat we de download
# afbreken. Dit is een geheugengrens, geen inhoudelijke: `getraw` kent geen
# bovengrens aan wat het teruggeeft, en de container wel.
#
# Gemeten op de stukken die de import op 23 september langshaalde: 45 KB,
# 7 MB, 16 MB, en 2026D43577 van 128 MB. Die laatste komt als bytes binnen,
# gaat als string door de PDF-parser en kost daarmee een veelvoud van zijn
# eigen omvang. De pod werd er herhaaldelijk om gekilled: OOMKilled bij een
# limiet van 961Mi, die het platform al twee keer automatisch had opgehoogd.
# Inmiddels staat die op 2 GB, wat de uitschieter dempt maar niet weghaalt
# zolang de bron zelf geen bovengrens kent. En omdat `markeer_ingehaald` pas
# ná de hele ronde draait, bleef `ingehaald_op` NULL: de volgende ronde
# haalde precies dezelfde stukken opnieuw op. Negentien uur lang, zonder dat
# één ronde afrondde.
#
# 20 MB laat alles door wat we in productie zagen op die ene uitschieter na.
# Een stuk daarboven is een bijlagenbundel of een scan, en `knip_rond_termen`
# geeft het model toch maar 9.000 tekens: de rest was altijd al weggegooid
# werk.
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


@dataclass
class TkconvItem:
    """Eén treffer uit de zoek-RSS."""

    document_nummer: str
    titel: str
    commissie: str | None
    onderwerp: str | None
    link: str
    gepubliceerd_op: datetime | None
    # Welke zoektermen dit document aandroegen. Wordt gevuld door de
    # zoekronde, niet door de feed zelf.
    matched_terms: list[str] = field(default_factory=list)

    @property
    def document_url(self) -> str:
        """Publieke URL naar het stuk op tkconv."""
        return f"{BASE_URL}/document.html?nummer={self.document_nummer}"

    @property
    def raw_url(self) -> str:
        """URL naar het ruwe bestand.

        Let op het pad-segment: `getraw/<nr>` werkt, `getraw?nummer=<nr>`
        geeft 404.
        """
        return f"{BASE_URL}/getraw/{self.document_nummer}"


# feed-URL (inclusief query) -> laatst geziene ETag.
#
# Deze cache staat op moduleniveau en niet op de client, omdat de
# import-service elke ronde een verse client bouwt. Op de instantie zou de
# cache dus altijd leeg zijn: elke ronde stuurt dan geen `If-None-Match`,
# krijgt 200 met de volle body terug in plaats van een 304 van 0 bytes, en
# de hele besparing waarop het twee-minuten-ritme berust verdampt — 360
# volledige GET's per dag op een feed van een halve megabyte.
#
# Toestand op moduleniveau leeft zo lang als het workerproces. Dat is
# precies de bedoelde levensduur: het is een optimalisatie, niet iets wat
# een herstart hoeft te overleven. Na een herstart is het één volle GET per
# feed en daarna weer 304's.
_ETAGS: dict[str, str] = {}


def reset_etag_cache() -> None:
    """Leeg de ETag-cache. Voor tests, zodat die elkaar niet beïnvloeden."""
    _ETAGS.clear()


class TkconvClient:
    """Bevraagt de zoek-RSS en haalt documentteksten op."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self._http_client: httpx.AsyncClient | None = None
        self._etags = _ETAGS

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(SEARCH_TIMEOUT),
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    # De feeds zijn XML en comprimeren tot ~10%.
                    "Accept-Encoding": "gzip",
                },
            )
        return self._http_client

    async def globale_feed_gewijzigd(self) -> bool | None:
        """Is er sinds de vorige ronde iets nieuws verschenen?

        `/index.xml` draagt alle stukken van de afgelopen acht dagen en
        verandert zodra er één bij komt. Eén HEAD met een bekende ETag
        kost 0 bytes body en vertelt of de zoektermen überhaupt bevraagd
        hoeven worden. Dat maakt een ronde van twee minuten goedkoper voor
        Berts server dan het uurlijkse rondje dat er eerst stond.

        Geeft True (er is iets nieuws), False (niets gewijzigd), of None
        als de klopper zelf niet werkte — dan zoeken we gewoon door, want
        een kapotte optimalisatie mag geen gemiste alert opleveren.
        """
        client = self._get_http_client()
        url = f"{self.base_url}/index.xml"
        headers = {}
        vorige = self._etags.get(url)
        if vorige:
            headers["If-None-Match"] = vorige

        try:
            response = await client.head(url, headers=headers)
        except httpx.RequestError as e:
            logger.warning("tkconv-klopper onbereikbaar: %s", e)
            return None

        if response.status_code == 304:
            return False
        if response.status_code != 200:
            logger.warning("tkconv-klopper gaf %s", response.status_code)
            return None

        etag = response.headers.get("etag")
        if not etag:
            # Zonder ETag kan de klopper niets uitsluiten.
            return None
        if vorige is None:
            # Eerste ronde: we weten niet of er iets nieuws is.
            self._etags[url] = etag
            return None
        gewijzigd = etag != vorige
        self._etags[url] = etag
        return gewijzigd

    async def close(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "TkconvClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def search(
        self, query: str, *, negeer_cache: bool = False
    ) -> list[TkconvItem]:
        """Zoek op één term en geef de treffers terug.

        `query` moet al gequote zijn voor een frase — zie
        `ParlementairAbonnement.zoekopdracht()`. Een ongequote meerwoordsterm
        OR't de woorden en levert willekeurige treffers op.

        `negeer_cache` slaat de ETag over. Nodig wanneer de aanroeper de
        volledige feed moet zien en niet alleen wat er sinds de vorige
        ronde bij kwam: een verse zoekterm die zijn inhaalslag doet, of een
        meting die de werkelijke trefferaantallen nodig heeft. De cache zit
        op de query en weet niets van wie er zoekt.
        """
        client = self._get_http_client()
        url = f"{self.base_url}/search/index.xml"
        cache_key = f"{url}?q={query}"

        headers = {}
        vorige = None if negeer_cache else self._etags.get(cache_key)
        if vorige:
            headers["If-None-Match"] = vorige

        try:
            response = await client.get(url, params={"q": query}, headers=headers)
            if response.status_code == 304:
                # Deze term leverde niets nieuws op sinds de vorige ronde.
                # Leeg teruggeven is correct: de items die er al waren zijn
                # allang geïmporteerd en zouden op zaak_id afketsen.
                return []
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                "tkconv-zoekopdracht %r faalde: %s %s",
                query,
                e.response.status_code,
                e.response.text[:200],
            )
            return []
        except httpx.RequestError as e:
            logger.error("tkconv onbereikbaar voor %r: %s", query, e)
            return []

        etag = response.headers.get("etag")
        if etag:
            self._etags[cache_key] = etag

        return self._parse_feed(response.content, query)

    @staticmethod
    def _parse_feed(payload: bytes, query: str) -> list[TkconvItem]:
        """Parse de RSS. Een formaatwijziging mag de poller niet omleggen."""
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as e:
            logger.error("tkconv gaf onleesbare XML voor %r: %s", query, e)
            return []

        items: list[TkconvItem] = []
        for node in root.findall(".//item"):

            def text_of(tag: str) -> str:
                el = node.find(tag)
                return (el.text or "").strip() if el is not None else ""

            guid = text_of("guid")
            # De guid heeft de vorm `tkconv_<documentnummer>` en is de
            # stabiele dedup-sleutel.
            nummer = guid.removeprefix("tkconv_").strip()
            if not nummer:
                logger.warning("tkconv-item zonder bruikbare guid: %r", guid)
                continue

            commissie, onderwerp = _split_description(text_of("description"))

            gepubliceerd = None
            pub = text_of("pubDate")
            if pub:
                try:
                    gepubliceerd = parsedate_to_datetime(pub)
                    if gepubliceerd.tzinfo is None:
                        gepubliceerd = gepubliceerd.replace(tzinfo=UTC)
                except (TypeError, ValueError):
                    logger.warning("tkconv-item %s heeft pubDate %r", nummer, pub)

            items.append(
                TkconvItem(
                    document_nummer=nummer,
                    titel=text_of("title") or nummer,
                    commissie=commissie,
                    onderwerp=onderwerp,
                    link=text_of("link") or f"{BASE_URL}/document.html?nummer={nummer}",
                    gepubliceerd_op=gepubliceerd,
                    matched_terms=[query],
                )
            )
        return items

    async def search_many(
        self,
        queries: list[str],
        pause_seconds: float = 1.0,
        negeer_cache: set[str] | None = None,
    ) -> list[TkconvItem]:
        """Zoek op meerdere termen en geef ontdubbelde documenten terug.

        Dedup is hier de kern, niet een detail. Bij een meting op 22
        september 2026 leverden elf termen 24 losse treffers op over maar
        acht unieke documenten; de startnotitie NLDD matchte op zeven
        termen tegelijk. Zonder ontdubbeling zou dat ene stuk zeven
        berichten opleveren.

        Het resultaat draagt per document álle termen die hem aandroegen,
        zodat het bericht kan tonen waaróm het binnenkwam.
        """
        gevonden: dict[str, TkconvItem] = {}
        zonder_cache = negeer_cache or set()
        for query in queries:
            for item in await self.search(query, negeer_cache=query in zonder_cache):
                bestaand = gevonden.get(item.document_nummer)
                if bestaand is None:
                    gevonden[item.document_nummer] = item
                elif query not in bestaand.matched_terms:
                    bestaand.matched_terms.append(query)
            # tkconv draait op andermans server; ga er rustig overheen.
            if pause_seconds > 0 and query != queries[-1]:
                await asyncio.sleep(pause_seconds)

        items = list(gevonden.values())
        items.sort(
            key=lambda i: i.gepubliceerd_op or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        logger.info(
            "tkconv: %d termen gaven %d unieke documenten",
            len(queries),
            len(items),
        )
        return items

    async def fetch_document_text(self, nummer: str) -> tuple[str | None, str | None]:
        """Haal de tekst van één document op.

        Geeft (tekst, content_type) terug. `getraw` levert niet altijd PDF:
        2026D45064 komt terug als docx. Daarom splitsen op content-type in
        plaats van op aanname.
        """
        client = self._get_http_client()
        url = f"{self.base_url}/getraw/{nummer}"

        # Streamend, met een grens op wat we binnenlaten. `client.get` leest
        # de hele response in het geheugen voordat wij er iets over kunnen
        # zeggen, en bij een document van 128 MB is dat precies de stap die
        # de container omver duwt. Zo stopt de download zodra de grens in
        # zicht komt, in plaats van erna.
        try:
            async with client.stream(
                "GET", url, timeout=httpx.Timeout(DOCUMENT_TIMEOUT)
            ) as response:
                response.raise_for_status()

                raw_type = response.headers.get("content-type") or ""
                content_type = raw_type.split(";")[0].strip()

                # De bron kent zijn eigen omvang meestal al. Die uitlezen
                # scheelt het binnenhalen van de eerste 20 MB van een stuk
                # dat we toch weggooien.
                aangekondigd = response.headers.get("content-length")
                if aangekondigd and int(aangekondigd) > MAX_DOCUMENT_BYTES:
                    logger.warning(
                        "getraw %s is %d MB en wordt overgeslagen (grens %d MB)",
                        nummer,
                        int(aangekondigd) // (1024 * 1024),
                        MAX_DOCUMENT_BYTES // (1024 * 1024),
                    )
                    return None, content_type

                brokken: list[bytes] = []
                omvang = 0
                async for brok in response.aiter_bytes():
                    omvang += len(brok)
                    if omvang > MAX_DOCUMENT_BYTES:
                        logger.warning(
                            "getraw %s overschrijdt %d MB tijdens het lezen "
                            "en wordt overgeslagen",
                            nummer,
                            MAX_DOCUMENT_BYTES // (1024 * 1024),
                        )
                        return None, content_type
                    brokken.append(brok)

                inhoud = b"".join(brokken)
        except httpx.HTTPStatusError as e:
            logger.warning("getraw %s gaf %s", nummer, e.response.status_code)
            return None, None
        except httpx.RequestError as e:
            logger.warning("getraw %s onbereikbaar: %s", nummer, e)
            return None, None

        text = _extract_text(inhoud, content_type, nummer)
        return text, content_type


def _split_description(description: str) -> tuple[str | None, str | None]:
    """Splits `commissie | onderwerp` uit de RSS-description.

    Niet elk item heeft een commissie; bijlagen komen binnen als `| onderwerp`.
    """
    if not description:
        return None, None
    if "|" in description:
        left, _, right = description.partition("|")
        return (left.strip() or None), (right.strip() or None)
    return None, description.strip() or None


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

SUFFIXES = {
    "application/pdf": ".pdf",
    DOCX_CONTENT_TYPE: ".docx",
    "application/vnd.oasis.opendocument.text": ".odt",
    "text/plain": ".txt",
}


def _sniff_content_type(payload: bytes, declared: str) -> str:
    """Bepaal het content-type, met de bytes als correctie op de header.

    `getraw` levert niet altijd wat je verwacht: 2026D45065 komt als PDF
    terug, 2026D45064 als docx. De header is doorgaans correct, maar een
    magic-byte-check kost niets en vangt een generieke
    `application/octet-stream` op.
    """
    if payload[:4] == b"%PDF":
        return "application/pdf"
    if payload[:2] == b"PK" and "wordprocessingml" in declared:
        return DOCX_CONTENT_TYPE
    if payload[:2] == b"PK" and "opendocument" in declared:
        return "application/vnd.oasis.opendocument.text"
    return declared


def _extract_text(payload: bytes, content_type: str, nummer: str) -> str | None:
    """Haal platte tekst uit het ruwe bestand.

    Delegeert aan `document_extract.extract_text`, dezelfde route die
    geüploade bijlagen nemen — inclusief de truncatie op 15.000 tekens die
    de LLM-prompt binnen de perken houdt. Die functie werkt op een pad, dus
    het antwoord gaat door een tempfile.

    Faalt zacht: zonder tekst kan het item nog steeds gemeld worden met
    alleen zijn titel, en dat is beter dan de hele ronde laten omvallen.
    """
    resolved = _sniff_content_type(payload, content_type)
    suffix = SUFFIXES.get(resolved)
    if suffix is None:
        logger.info("Onbekend content-type %r voor %s", resolved, nummer)
        return None

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        tekst = extract_text(tmp_path, resolved, max_chars=MAX_DOCUMENT_TEKENS)
        return tekst
    except Exception as e:  # noqa: BLE001 - extractie mag nooit de ronde stoppen
        logger.warning("Tekstextractie faalde voor %s (%s): %s", nummer, resolved, e)
        return None
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
