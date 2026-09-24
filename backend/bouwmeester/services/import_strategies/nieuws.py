"""Volgt zoektermen in vakmedia over de digitale overheid.

Dezelfde zoektermen als de kamerstukken, dezelfde signaalcontext, een ander
soort bron. Wat een dossier is, verandert niet met het medium: "fundament"
is in een artikel van Binnenlands Bestuur net zo goed een metafoor als in
een kamerbrief.

Twee dingen werken hier anders dan bij `TkconvSearchStrategy`, en allebei
volgen ze uit wat de bron levert:

Zoeken gebeurt aan onze kant. Een nieuws-RSS heeft geen zoekparameter, dus
we halen de feed één keer op en matchen alle abonnementen tegen titel plus
teaser. Eén verzoek per bron per ronde, ongeacht het aantal zoektermen.

De artikeltekst wordt per artikel opgehaald. Geen van beide feeds draagt
`content:encoded` (gemeten 23 september 2026), dus de feed levert alleen
een teaser van 131 tot 345 tekens. Dat bleek te weinig: "Strategische
inzet digitalisering" (iBestuur, 23 september 2026) heeft een teaser
waarin geen enkele zoekterm voorkomt, terwijl de body de NLDD en de
overheidscloud allebei noemt.

Alleen voor artikelen boven het watermerk, dus in de praktijk een handvol
per ronde en niet de 150 uit de feed. Mislukt het ophalen, dan geldt de
teaser: een scraper die stukloopt op een nieuwe opmaak mag geen artikelen
laten verdwijnen.
"""

import logging
from datetime import UTC, date, datetime

from bouwmeester.models.nieuwsbron import Nieuwsbron
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.nieuws_client import NieuwsClient, NieuwsItem

logger = logging.getLogger(__name__)

ITEM_TYPE = "nieuwsartikel"

# ETags overleven de ronde, want de import-service bouwt elke ronde een
# verse client. Op de instantie zou de conditional GET nooit raak zijn.
# Zelfde reden als het watermerk in `tkconv.py`.
_ETAGS: dict[str, str] = {}

# Het watermerk, op moduleniveau en om dezelfde reden als bij tkconv: op de
# instantie zou het elke ronde op "nu" staan, en dan komt er nooit iets
# door omdat elk artikel per definitie al gepubliceerd is.
_WATERMERK: datetime | None = None


def reset_watermerk() -> None:
    """Voor tests: zet het procesgeheugen terug."""
    global _WATERMERK
    _WATERMERK = None
    _ETAGS.clear()


class NieuwsStrategy(ImportStrategy):
    """Zoekt de abonnementen van alle initiatieven in de nieuwsfeeds."""

    def __init__(self) -> None:
        self.abonnementen: list[ParlementairAbonnement] = []
        self.bronnen: list[Nieuwsbron] = []
        # docnr -> abonnement-ids, zoals bij tkconv: `_process_item` legt
        # de treffers vast en heeft nodig welke term het stuk aandroeg.
        self.treffers: dict[str, list] = {}
        self.verse_abonnementen: set = set()

    @property
    def item_type(self) -> str:
        return ITEM_TYPE

    @property
    def politieke_input_type(self) -> str:
        return "nieuwsartikel"

    @property
    def requires_llm(self) -> bool:
        return True

    @property
    def supports_ek(self) -> bool:
        return False

    @property
    def uses_tk_api(self) -> bool:
        return False

    @property
    def always_import(self) -> bool:
        # De zoekterm is de scope-check, net als bij de kamerstukken.
        return True

    @property
    def creates_corpus_node(self) -> bool:
        return True

    def build_client(self) -> NieuwsClient:
        return NieuwsClient(etags=_ETAGS)

    async def fetch_items(
        self,
        client: object,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        global _WATERMERK

        if not isinstance(client, NieuwsClient):
            logger.error("NieuwsStrategy kreeg een %s", type(client).__name__)
            return []
        if not self.abonnementen or not self.bronnen:
            return []

        eerste_ronde = _WATERMERK is None
        grens = _WATERMERK

        artikelen: list[NieuwsItem] = []
        for bron in self.bronnen:
            artikelen.extend(await client.haal(bron.feed_url, bron.naam))

        # Oud naar nieuw, zodat een limiet de nieuwste artikelen overlaat
        # voor de volgende ronde in plaats van ze weg te gooien. Artikelen
        # zonder datum achteraan: die kunnen we niet plaatsen.
        artikelen.sort(key=lambda a: a.gepubliceerd or datetime.min.replace(tzinfo=UTC))

        resultaten: list[FetchedItem] = []
        nieuwste = grens
        for artikel in artikelen:
            wanneer = artikel.gepubliceerd
            if wanneer is not None and (nieuwste is None or wanneer > nieuwste):
                nieuwste = wanneer

            if grens is not None and wanneer is not None and wanneer <= grens:
                continue

            if eerste_ronde:
                # Zoals bij tkconv: de eerste ronde zet alleen het
                # watermerk. Anders opent de feature met een reeks
                # berichten over artikelen van vorige maand. Hier al
                # stoppen, vóór de fetch: 150 artikelpagina's ophalen om
                # er vervolgens nul te posten is verkeer voor niets.
                continue

            # De artikeltekst vóór het matchen, want juist in de body
            # staat vaak het woord dat de teaser niet noemt. Gemeten
            # geval: "Strategische inzet digitalisering" (iBestuur, 23
            # september 2026) heeft een teaser van 131 tekens zonder één
            # van de zoektermen, terwijl de body de NLDD en de
            # overheidscloud allebei noemt.
            #
            # Alleen voor artikelen boven het watermerk, dus een handvol
            # per ronde in plaats van de 150 uit de feed.
            if artikel.link:
                artikel.volledige_tekst = await client.haal_artikel(artikel.link)

            ids = self._passende_abonnementen(artikel)
            if not ids:
                continue

            self.treffers[artikel.gid] = ids
            resultaten.append(self._naar_item(artikel))
            if len(resultaten) >= limit:
                break

        _WATERMERK = nieuwste or datetime.now(UTC)
        if eerste_ronde:
            logger.info(
                "Nieuws: eerste ronde, watermerk gezet op %s (%d artikelen gelezen)",
                _WATERMERK,
                len(artikelen),
            )
        return resultaten

    def _passende_abonnementen(self, artikel: NieuwsItem) -> list:
        """Welke zoektermen komen voor in titel of teaser?

        Kleine letters aan beide kanten: een kop schrijft "Digitale
        Dienst" waar de term "digitale dienst" is, en dat is dezelfde
        treffer. De frase-vorm van tkconv (aanhalingstekens) heeft hier
        geen betekenis, want we matchen zelf op de hele string.
        """
        tekst = artikel.doorzoekbare_tekst.lower()
        return [
            a.id
            for a in self.abonnementen
            if a.actief and a.term_genormaliseerd and a.term_genormaliseerd in tekst
        ]

    def _naar_item(self, artikel: NieuwsItem) -> FetchedItem:
        return FetchedItem(
            zaak_id=artikel.gid,
            zaak_nummer=artikel.gid,
            titel=artikel.titel,
            onderwerp=artikel.samenvatting,
            datum=artikel.gepubliceerd.date() if artikel.gepubliceerd else None,
            # Precies de tekst waarin ook gezocht is: titel, teaser en de
            # artikeltekst als die is opgehaald. Het model krijgt niet
            # meer dan wij zagen, en niet minder.
            document_tekst=artikel.doorzoekbare_tekst,
            document_url=artikel.link,
            bron=artikel.bron,
            extra_data={
                "categorie": "nieuws",
                "soort": "Nieuwsartikel",
                "publicatie": artikel.bron,
            },
        )
