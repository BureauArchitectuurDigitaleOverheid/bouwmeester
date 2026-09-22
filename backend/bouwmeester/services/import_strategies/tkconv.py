"""Tkconv import strategy — volgt zoektermen in de volledige tekst van kamerstukken.

Waarom naast de bestaande strategieën, die allemaal via `tk_api_client` bij
de officiële OData-API ophalen: die API doorzoekt alleen metadata. Een
meting op 22 september 2026 over "Nederlandse Digitale Dienst" en
"Regelrecht" gaf **nul** overlap tussen wat de zaak-API oplevert en wat
tkconv vindt. Twee oorzaken, allebei structureel:

- Een bijlage heeft geen Zaak-koppeling. 2026D45065 ("Startnotitie
  Nederlandse Digitale Dienst") hangt via BronDocument aan een kamerbrief
  en is zaak-gebaseerd onbereikbaar.
- De term staat vaak alleen in de body. 2026D45064 heet "Strategische inzet
  digitalisering"; pas in de tekst staat dat RegelRecht uitwerkt hoe
  wetgeving naar uitvoerbare code vertaald wordt.

Deze strategie wijkt op drie punten af van de andere:

- `always_import = True` — de zoekterm ís de scope-check. Een item zonder
  gematchte corpusknopen is nog steeds relevant.
- `supports_ek = False` — tkconv indexeert de Tweede Kamer.
- `creates_corpus_node = True` — de koppeling aan corpusknopen is juist de
  opbrengst die een losse alert-tool niet kan geven.
"""

import logging
from datetime import UTC, date, datetime

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.tkconv_client import TkconvClient, TkconvItem

logger = logging.getLogger(__name__)

ITEM_TYPE = "tkconv_document"

# Bij de eerste ronde voor een nieuwe term importeren we geen backlog. De
# zoek-RSS draagt ongeveer een week aan stukken; die in één keer posten zou
# de feature openen met een reeks berichten over stukken die niemand
# gevraagd heeft. De eerste ronde zet alleen het watermerk.
EERSTE_RONDE_IMPORTEERT = False


class TkconvSearchStrategy(ImportStrategy):
    """Volgt zoektermen via de tkconv-zoek-RSS."""

    def __init__(
        self,
        abonnementen: list[ParlementairAbonnement] | None = None,
        *,
        importeer_backlog: bool = EERSTE_RONDE_IMPORTEERT,
    ) -> None:
        """
        Args:
            abonnementen: de actieve abonnementen waarvoor gezocht wordt.
                Leeg betekent: niets te doen, geen fout.
            importeer_backlog: alles importeren wat de feed draagt, ook
                stukken van voor het abonnement. Standaard uit.
        """
        self.abonnementen = abonnementen or []
        self.importeer_backlog = importeer_backlog
        # Gevuld tijdens fetch_items: documentnummer -> abonnement-ids.
        # De aanroeper gebruikt dit om treffers vast te leggen.
        self.treffers: dict[str, list] = {}

    @property
    def item_type(self) -> str:
        return ITEM_TYPE

    @property
    def politieke_input_type(self) -> str:
        return "kamerstuk"

    @property
    def requires_llm(self) -> bool:
        return True

    @property
    def supports_ek(self) -> bool:
        return False

    @property
    def uses_tk_api(self) -> bool:
        return False

    def build_client(self) -> TkconvClient:
        return TkconvClient()

    @property
    def always_import(self) -> bool:
        # De zoekterm is de scope-check. Zonder dit zou een stuk dat op
        # "RegelRecht" matcht maar geen corpusknoop raakt als out_of_scope
        # wegvallen, en dat is precies het stuk dat we wilden zien.
        return True

    @property
    def creates_corpus_node(self) -> bool:
        return True

    async def fetch_items(
        self,
        client: object,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        if not isinstance(client, TkconvClient):
            logger.error("TkconvSearchStrategy kreeg een %s", type(client).__name__)
            return []
        if not self.abonnementen:
            return []

        # Eerst kloppen: is er sinds de vorige ronde überhaupt iets
        # verschenen? Eén HEAD op de globale feed kost 0 bytes body als de
        # ETag gelijk is, en maakt zo een ronde van twee minuten goedkoper
        # voor Berts server dan het uurlijkse rondje dat er eerst stond.
        # Alleen een hard "niets gewijzigd" slaat de zoektermen over; een
        # kapotte klopper (None) laat de ronde gewoon doorlopen, want een
        # mislukte optimalisatie mag geen gemiste alert opleveren.
        if await client.globale_feed_gewijzigd() is False:
            logger.debug("tkconv: niets nieuws sinds de vorige ronde")
            return []

        # Zoek per unieke zoekopdracht, niet per abonnement: twee
        # initiatieven die dezelfde term volgen leveren één HTTP-call op.
        per_query: dict[str, list[ParlementairAbonnement]] = {}
        for abonnement in self.abonnementen:
            per_query.setdefault(abonnement.zoekopdracht(), []).append(abonnement)

        items = await client.search_many(list(per_query))

        drempel = self._drempel(since)
        resultaten: list[FetchedItem] = []
        self.treffers = {}

        for item in items:
            if drempel and item.gepubliceerd_op and item.gepubliceerd_op < drempel:
                continue

            abonnement_ids = []
            for query in item.matched_terms:
                for abonnement in per_query.get(query, []):
                    if abonnement.id not in abonnement_ids:
                        abonnement_ids.append(abonnement.id)
            if not abonnement_ids:
                continue

            tekst, content_type = await client.fetch_document_text(item.document_nummer)
            self.treffers[item.document_nummer] = abonnement_ids
            resultaten.append(self._to_fetched_item(item, tekst, content_type))

        logger.info(
            "tkconv: %d van %d documenten na de datumdrempel",
            len(resultaten),
            len(items),
        )
        return resultaten[:limit]

    def _drempel(self, since: date | None) -> datetime | None:
        """Vanaf wanneer een stuk meetelt.

        Zonder `since` en zonder backlog-vlag telt niets mee: dat is de
        eerste ronde, die alleen het watermerk zet.
        """
        if since is not None:
            return datetime.combine(since, datetime.min.time(), tzinfo=UTC)
        if self.importeer_backlog:
            return None
        return datetime.now(UTC)

    @staticmethod
    def _to_fetched_item(
        item: TkconvItem, tekst: str | None, content_type: str | None
    ) -> FetchedItem:
        # `zaak_id` draagt het documentnummer: dat is de stabiele
        # dedup-sleutel uit de guid, en `_import_item` checkt er al op via
        # `get_by_zaak_id`. Zo werkt idempotentie zonder schemawijziging.
        return FetchedItem(
            zaak_id=item.document_nummer,
            zaak_nummer=item.document_nummer,
            titel=item.titel,
            onderwerp=item.onderwerp or item.titel,
            datum=item.gepubliceerd_op.date() if item.gepubliceerd_op else None,
            indieners=[],
            document_tekst=tekst,
            document_url=item.document_url,
            bron="tweede_kamer",
            extra_data={
                "herkomst": "tkconv",
                "commissie": item.commissie,
                "matched_terms": item.matched_terms,
                "raw_url": item.raw_url,
                "content_type": content_type,
            },
        )

    def task_title(self, item: FetchedItem) -> str:
        onderwerp = (item.onderwerp or item.titel or "onbekend")[:80]
        return f"Beoordeel kamerstuk: {onderwerp}"

    def task_priority(self, item: FetchedItem) -> str:
        # Een signaal, geen deadline. Moties en kamervragen houden 'hoog'.
        return "normaal"

    def notification_title(self, node_title: str) -> str:
        return f"Nieuw kamerstuk: {node_title}"

    def context_hint(self) -> str:
        return "kamerstuk gevonden via zoekterm in de volledige tekst"
