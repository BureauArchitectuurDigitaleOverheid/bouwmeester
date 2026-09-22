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
from zoneinfo import ZoneInfo

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.kamerstuk_soort import KamerstukContext, haal_context
from bouwmeester.services.tkconv_client import TkconvClient, TkconvItem

logger = logging.getLogger(__name__)

ITEM_TYPE = "tkconv_document"

# De feed levert pubDate in Nederlandse tijd; de poller draait op dezelfde
# zone (zie worker._AMSTERDAM).
_AMSTERDAM = ZoneInfo("Europe/Amsterdam")

# Bij de eerste ronde voor een nieuwe term importeren we geen backlog. De
# zoek-RSS draagt ongeveer een week aan stukken; die in één keer posten zou
# de feature openen met een reeks berichten over stukken die niemand
# gevraagd heeft. De eerste ronde zet alleen het watermerk.
EERSTE_RONDE_IMPORTEERT = False

# Het watermerk: alles dat later is verschenen dan dit tijdstip telt mee.
#
# Dit staat op moduleniveau en niet op de instantie, omdat de import-service
# elke ronde een verse strategie bouwt. Op de instantie zou het watermerk
# elke ronde opnieuw op "nu" staan, en dan komt er nooit iets door: een
# stuk uit de feed is per definitie al gepubliceerd, dus altijd ouder dan
# het moment waarop de ronde draait. De feature importeerde daardoor
# structureel nul stukken.
#
# Procesgeheugen is hier de juiste levensduur. Na een herstart is het
# watermerk weer "nu", dus een stuk dat precies tijdens die herstart
# verscheen kan wegvallen. Dat is een bewuste afweging: de dedup op
# documentnummer zit in de database, dus het alternatief (watermerk in de
# database) koopt alleen dat ene randgeval af, en kost een schrijfactie per
# ronde plus een migratie.
_WATERMERK: datetime | None = None


def reset_watermerk() -> None:
    """Zet het watermerk terug. Voor tests, zodat die elkaar niet raken."""
    global _WATERMERK  # noqa: PLW0603
    _WATERMERK = None


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
        # De abonnementen die deze ronde hun eenmalige inhaalslag doen.
        # De aanroeper splitst daarop: die krijgen één samenvattend
        # bericht, de andere abonnees een losse alert.
        #
        # Alleen de ids, niet de gevonden stukken: welke stukken er
        # daadwerkelijk bij horen blijkt pas ná de idempotency-check in
        # `_process_item`, en een stuk dat al binnen was mag geen
        # treffer-loze vermelding in het inhaalbericht opleveren.
        self.verse_abonnementen: set = set()

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

        # Een verse term moet de feed zien, ook als de poller die query al
        # eerder heeft gedaan: de ETag-cache zit op de query, niet op het
        # abonnement, en zou anders een 304 met een lege lijst geven.
        verse_queries = {
            query
            for query, abos in per_query.items()
            if any(a.ingehaald_op is None for a in abos)
        }
        items = await client.search_many(list(per_query), negeer_cache=verse_queries)
        # Oud naar nieuw verwerken. `search_many` sorteert nieuw-eerst, en
        # met de `limit`-break zou dat de oudste stukken laten liggen —
        # precies degene die daarna onder het opgeschoven watermerk
        # vallen en dus nooit meer langskomen.
        items = list(reversed(items))

        drempel = self._drempel(since)
        resultaten: list[FetchedItem] = []
        afgekapt = False
        self.treffers = {}
        self.verse_abonnementen = {
            a.id for a in self.abonnementen if a.ingehaald_op is None
        }

        for item in items:
            # De drempel geldt per abonnement, niet per stuk: een term die
            # vandaag is toegevoegd heeft nog geen inhaalslag gehad en mag
            # de hele feed zien (dat is meestal juist de aanleiding om hem
            # toe te voegen), terwijl een term die al loopt alleen nieuwe
            # stukken krijgt.
            abonnement_ids = []
            for query in item.matched_terms:
                for abonnement in per_query.get(query, []):
                    if abonnement.id in abonnement_ids:
                        continue
                    if self._telt_mee(abonnement, item, drempel):
                        abonnement_ids.append(abonnement.id)
            if not abonnement_ids:
                continue

            # Afkappen vóór het ophalen van de tekst: anders halen we
            # documenten op bij Berts server die we daarna weggooien.
            if len(resultaten) >= limit:
                afgekapt = True
                logger.warning(
                    "tkconv: meer dan %d treffers in één ronde, rest volgt "
                    "de volgende ronde",
                    limit,
                )
                break

            tekst, content_type = await client.fetch_document_text(item.document_nummer)
            # Wat voor stuk is dit? tkconv levert dat niet, de officiële
            # API wel. Eén call per nieuw stuk, niet per ronde: het soort
            # bepaalt de vorm van het bericht en wat de LLM ervan moet
            # maken, en zonder dit heet alles "Kamerstuk".
            context = await haal_context(
                item.document_nummer, client._get_http_client()
            )
            self.treffers[item.document_nummer] = abonnement_ids
            resultaten.append(self._to_fetched_item(item, tekst, content_type, context))

        self._verschuif_watermerk(items, resultaten, afgekapt)

        logger.info(
            "tkconv: %d van %d documenten na de datumdrempel",
            len(resultaten),
            len(items),
        )
        return resultaten

    @staticmethod
    def _verschuif_watermerk(
        items: list[TkconvItem], resultaten: list[FetchedItem], afgekapt: bool
    ) -> None:
        """Schuif het watermerk op tot waar deze ronde is gekomen.

        Niet naar "nu": tussen het ophalen van de feed en dit moment kan
        een stuk verschijnen dat we nog niet gezien hebben, en dat zou dan
        stil wegvallen. Het nieuwste verwerkte tijdstip is de enige grens
        die we echt kunnen verantwoorden.

        Bij een afgekapte ronde is dat nieuwste verwerkte tijdstip nog
        steeds veilig, want de items worden oud-naar-nieuw verwerkt: alles
        wat blijft liggen is jonger dan wat we hebben gedaan. Zo kruipt de
        grens elke ronde een stukje op tot de achterstand is ingelopen,
        zonder ooit over iets ongeziens heen te gaan.

        Het omgekeerde (nieuw-naar-oud, zoals de feed sorteert) zou de
        oudste stukken permanent onder het watermerk begraven.
        """
        global _WATERMERK  # noqa: PLW0603

        verwerkt = {r.zaak_id for r in resultaten}
        tijden = [
            i.gepubliceerd_op
            for i in items
            if i.gepubliceerd_op and i.document_nummer in verwerkt
        ]
        if not tijden:
            # Niets verwerkt. Bij een eerste ronde (watermerk nog leeg) is
            # dat het moment om te beginnen; anders blijft het staan, zodat
            # een ronde zonder treffers niets overslaat.
            if _WATERMERK is None and not afgekapt:
                _WATERMERK = datetime.now(UTC)
            return

        nieuwste = max(tijden)
        if _WATERMERK is None or nieuwste > _WATERMERK:
            _WATERMERK = nieuwste

    @staticmethod
    def _telt_mee(
        abonnement: ParlementairAbonnement,
        item: TkconvItem,
        drempel: datetime | None,
    ) -> bool:
        """Mag dit stuk voor dit abonnement meetellen?

        Een abonnement zonder `ingehaald_op` doet zijn eenmalige
        inhaalslag: alles wat de feed draagt telt mee. Daarna geldt het
        gewone watermerk.
        """
        if abonnement.ingehaald_op is None:
            return True
        if drempel is None or item.gepubliceerd_op is None:
            return True
        return item.gepubliceerd_op > drempel

    def _drempel(self, since: date | None) -> datetime | None:
        """Vanaf wanneer een stuk meetelt.

        `since` wint als de aanroeper hem meegeeft; de poller doet dat niet,
        die leunt op het watermerk uit de vorige ronde. Is dat er nog niet
        (eerste ronde na een start), dan is de drempel "nu": dan importeren
        we de backlog van een week niet, maar alles wat daarna verschijnt
        wel.
        """
        if since is not None:
            # De feed levert `pubDate` in Nederlandse tijd en de poller
            # draait op Europe/Amsterdam, dus een kale datum hoort ook in
            # die zone te worden uitgelegd. Met UTC zou een stuk van
            # 00:30 Amsterdam op de grensdag wegvallen.
            return datetime.combine(since, datetime.min.time(), tzinfo=_AMSTERDAM)
        if self.importeer_backlog:
            return None
        # Geen watermerk betekent: eerste ronde na een start. Dan is de
        # grens "nu", zodat de backlog van een week niet in één keer wordt
        # gepost. `None` zou hier "geen grens" betekenen en precies dat
        # veroorzaken.
        return _WATERMERK if _WATERMERK is not None else datetime.now(UTC)

    @staticmethod
    def _to_fetched_item(
        item: TkconvItem,
        tekst: str | None,
        content_type: str | None,
        context: KamerstukContext | None = None,
    ) -> FetchedItem:
        # `zaak_id` draagt het documentnummer: dat is de stabiele
        # dedup-sleutel uit de guid, en `_import_item` checkt er al op via
        # `get_by_zaak_id`. Zo werkt idempotentie zonder schemawijziging.
        context = context or KamerstukContext()
        extra = {
            "herkomst": "tkconv",
            "commissie": item.commissie,
            "matched_terms": item.matched_terms,
            "raw_url": item.raw_url,
            "content_type": content_type,
        }
        extra.update(context.as_extra_data())
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
            # Bij een kamervraag is de antwoordtermijn een echte deadline;
            # de pipeline zet die op de review-taak.
            deadline=context.termijn,
            extra_data=extra,
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
