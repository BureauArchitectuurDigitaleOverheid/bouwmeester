"""Tests voor de tkconv-client en de zoekterm-strategie.

De fixtures zijn echte RSS-vormen zoals de feed ze op 22 september 2026
leverde, met de documentnummers erin. Dat is bewust: de twee gevallen die
het ontwerp bepalen (een bijlage zonder zaak-koppeling, en een stuk dat
alleen in de body matcht) zijn allebei publieke kamerstukken.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services import tkconv_client
from bouwmeester.services.import_strategies.tkconv import (
    TkconvSearchStrategy,
    reset_watermerk,
)
from bouwmeester.services.tkconv_client import (
    MAX_DOCUMENT_BYTES,
    TkconvClient,
    TkconvItem,
    _split_description,
    reset_etag_cache,
)
from bouwmeester.worker import _AMSTERDAM

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Startnotitie Nederlandse Digitale Dienst</title>
  <description>|  Startnotitie Nederlandse Digitale Dienst</description>
  <link>https://berthub.eu/tkconv/document.html?nummer=2026D45065</link>
  <guid>tkconv_2026D45065</guid>
  <pubDate>Mon, 21 Sep 2026 17:09:57 +0200</pubDate>
</item>
<item>
  <title>Strategische inzet digitalisering</title>
  <description>vaste commissie voor Digitale Zaken |  Strategische inzet</description>
  <link>https://berthub.eu/tkconv/document.html?nummer=2026D45064</link>
  <guid>tkconv_2026D45064</guid>
  <pubDate>Mon, 21 Sep 2026 17:09:57 +0200</pubDate>
</item>
</channel></rss>"""


class TestFeedParsing:
    def test_parses_items(self):
        items = TkconvClient._parse_feed(FEED, '"Nederlandse Digitale Dienst"')
        assert [i.document_nummer for i in items] == ["2026D45065", "2026D45064"]

    def test_guid_is_the_dedup_key(self):
        items = TkconvClient._parse_feed(FEED, "x")
        # De guid draagt `tkconv_`-prefix; het documentnummer erachter is
        # wat `get_by_zaak_id` straks vergelijkt.
        assert items[0].document_nummer == "2026D45065"

    def test_raw_url_uses_path_segment(self):
        items = TkconvClient._parse_feed(FEED, "x")
        # `getraw?nummer=` geeft 404; het moet een pad-segment zijn.
        assert items[0].raw_url.endswith("/getraw/2026D45065")
        assert "?" not in items[0].raw_url

    def test_pubdate_is_timezone_aware(self):
        items = TkconvClient._parse_feed(FEED, "x")
        assert items[0].gepubliceerd_op is not None
        assert items[0].gepubliceerd_op.tzinfo is not None

    def test_broken_xml_returns_empty_not_raises(self):
        # Een formaatwijziging bij een ongedocumenteerd endpoint mag de
        # poll-ronde niet omleggen.
        assert TkconvClient._parse_feed(b"<rss><nope", "x") == []

    def test_item_without_guid_is_skipped(self):
        feed = b"<rss><channel><item><title>Geen guid</title></item></channel></rss>"
        assert TkconvClient._parse_feed(feed, "x") == []


class TestDescription:
    def test_splits_commissie_and_onderwerp(self):
        assert _split_description("vaste commissie voor DiZa |  Onderwerp") == (
            "vaste commissie voor DiZa",
            "Onderwerp",
        )

    def test_bijlage_has_no_commissie(self):
        # Bijlagen komen binnen als `| onderwerp`, zonder commissie.
        assert _split_description("|  Startnotitie") == (None, "Startnotitie")

    def test_empty(self):
        assert _split_description("") == (None, None)


def _abonnement(
    term: str, *, is_frase: bool = True, ingehaald: bool = True
) -> ParlementairAbonnement:
    """Een abonnement voor tests.

    `ingehaald=True` is de standaard omdat de meeste tests het gedrag ná
    de eenmalige inhaalslag toetsen: een verse term haalt bewust op wat de
    feed draagt, en dan zegt een watermerk-test niets.
    """
    a = ParlementairAbonnement(
        scope_type="initiatief",
        scope_id=uuid4(),
        term=term,
        term_genormaliseerd=ParlementairAbonnement.normaliseer(term),
        is_frase=is_frase,
    )
    a.id = uuid4()
    a.ingehaald_op = datetime(2026, 1, 1, tzinfo=UTC) if ingehaald else None
    return a


class TestZoekopdracht:
    def test_phrase_is_quoted(self):
        # Ongequote meerwoordstermen OR'en de woorden bij tkconv en leveren
        # dan willekeurige treffers op.
        assert _abonnement("Nederlandse Digitale Dienst").zoekopdracht() == (
            '"Nederlandse Digitale Dienst"'
        )

    def test_non_phrase_is_bare(self):
        assert _abonnement("NLDD", is_frase=False).zoekopdracht() == "NLDD"

    def test_normalisation_is_case_insensitive(self):
        # 'RegelRecht' en 'regelrecht' zijn hetzelfde abonnement.
        assert ParlementairAbonnement.normaliseer("  RegelRecht ") == "regelrecht"

    def test_normalisation_collapses_whitespace(self):
        assert ParlementairAbonnement.normaliseer('"Digitale   Dienst"') == (
            "digitale dienst"
        )


class _FakeClient(TkconvClient):
    """Client die de feed uit geheugen serveert."""

    def __init__(
        self,
        per_query: dict[str, list[TkconvItem]],
        *,
        feed_gewijzigd: bool | None = True,
    ):
        super().__init__()
        self.per_query = per_query
        self.feed_gewijzigd = feed_gewijzigd
        self.opgehaalde_documenten: list[str] = []
        self.zoekopdrachten: list[str] = []
        self.cache_omzeild: list[str] = []

    async def globale_feed_gewijzigd(self) -> bool | None:
        return self.feed_gewijzigd

    async def search(
        self, query: str, *, negeer_cache: bool = False
    ) -> list[TkconvItem]:
        self.zoekopdrachten.append(query)
        if negeer_cache:
            self.cache_omzeild.append(query)
        return [
            TkconvItem(**{**i.__dict__, "matched_terms": [query]})
            for i in self.per_query.get(query, [])
        ]

    async def fetch_document_text(self, nummer: str):
        self.opgehaalde_documenten.append(nummer)
        return f"tekst van {nummer}", "application/pdf"


def _item(nummer: str, dt: datetime) -> TkconvItem:
    return TkconvItem(
        document_nummer=nummer,
        titel=f"Stuk {nummer}",
        commissie=None,
        onderwerp="Onderwerp",
        link="",
        gepubliceerd_op=dt,
    )


class TestSearchMany:
    @pytest.mark.asyncio
    async def test_dedupes_across_terms(self):
        """Eén document op meerdere termen levert één item met beide termen.

        Gemeten geval: de startnotitie NLDD matchte op zeven van de elf
        geteste termen. Zonder ontdubbeling zou dat zeven berichten geven.
        """
        gedeeld = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [gedeeld], '"RegelRecht"': [gedeeld]})

        items = await client.search_many(['"NLDD"', '"RegelRecht"'], pause_seconds=0)

        assert len(items) == 1
        assert sorted(items[0].matched_terms) == ['"NLDD"', '"RegelRecht"']

    @pytest.mark.asyncio
    async def test_sorts_newest_first(self):
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        nieuw = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"x"': [oud, nieuw]})

        items = await client.search_many(['"x"'], pause_seconds=0)

        assert [i.document_nummer for i in items] == ["2026D45065", "2026D38772"]


class TestStrategy:
    def test_does_not_use_the_tk_odata_api(self):
        # De officiële API doorzoekt alleen metadata; daarom een eigen bron.
        s = TkconvSearchStrategy()
        assert s.uses_tk_api is False
        assert isinstance(s.build_client(), TkconvClient)

    def test_always_imports(self):
        # De zoekterm ís de scope-check: een stuk zonder corpusknoop mag
        # niet als out_of_scope wegvallen.
        assert TkconvSearchStrategy().always_import is True

    def test_no_eerste_kamer(self):
        assert TkconvSearchStrategy().supports_ek is False

    @pytest.mark.asyncio
    async def test_without_subscriptions_does_nothing(self):
        s = TkconvSearchStrategy(abonnementen=[])
        assert await s.fetch_items(client=_FakeClient({}), since=None, limit=10) == []

    @pytest.mark.asyncio
    async def test_first_run_imports_no_backlog(self):
        """De eerste ronde zet alleen het watermerk.

        De feed draagt circa een week aan stukken. Die bij het aanzetten
        van een term allemaal posten zou de feature openen met een reeks
        berichten over stukken waar niemand om vroeg.
        """
        a = _abonnement("NLDD")
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [oud]})

        s = TkconvSearchStrategy(abonnementen=[a])
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert resultaten == []
        # En er is geen document opgehaald: dat scheelt Berts server werk.
        assert client.opgehaalde_documenten == []

    @pytest.mark.asyncio
    async def test_backlog_flag_imports_everything(self):
        a = _abonnement("NLDD")
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [oud]})

        s = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert [r.zaak_nummer for r in resultaten] == ["2026D38772"]

    @pytest.mark.asyncio
    async def test_since_filters_older_items(self):
        a = _abonnement("NLDD")
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        nieuw = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [oud, nieuw]})

        s = TkconvSearchStrategy(abonnementen=[a])
        resultaten = await s.fetch_items(
            client=client, since=date(2026, 9, 20), limit=10
        )

        assert [r.zaak_nummer for r in resultaten] == ["2026D45065"]

    @pytest.mark.asyncio
    async def test_document_number_becomes_zaak_id(self):
        """Idempotentie leunt op `get_by_zaak_id`, dus het nummer moet daar in."""
        a = _abonnement("NLDD")
        nieuw = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [nieuw]})

        s = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert resultaten[0].zaak_id == "2026D45065"

    @pytest.mark.asyncio
    async def test_records_which_subscriptions_matched(self):
        a1 = _abonnement("NLDD")
        a2 = _abonnement("RegelRecht")
        gedeeld = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [gedeeld], '"RegelRecht"': [gedeeld]})

        s = TkconvSearchStrategy(abonnementen=[a1, a2], importeer_backlog=True)
        await s.fetch_items(client=client, since=None, limit=10)

        assert sorted(s.treffers["2026D45065"]) == sorted([a1.id, a2.id])
        # Eén document, dus één keer opgehaald ondanks twee termen.
        assert client.opgehaalde_documenten == ["2026D45065"]

    @pytest.mark.asyncio
    async def test_shared_term_queries_once(self):
        """Twee initiatieven op dezelfde term geven één HTTP-call."""
        a1 = _abonnement("NLDD")
        a2 = _abonnement("nldd")  # zelfde term, ander initiatief
        stuk = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [stuk], '"nldd"': [stuk]})

        s = TkconvSearchStrategy(abonnementen=[a1, a2], importeer_backlog=True)
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert len(resultaten) == 1
        assert sorted(s.treffers["2026D45065"]) == sorted([a1.id, a2.id])


class TestKlopper:
    """De globale feed als goedkope trigger vóór de zoektermen."""

    @pytest.mark.asyncio
    async def test_unchanged_feed_skips_all_searches(self):
        """Niets nieuws? Dan geen enkele zoekterm bevragen.

        Dit is wat een ronde van twee minuten betaalbaar maakt: één HEAD
        met een bekende ETag kost 0 bytes body, in plaats van één GET per
        term.
        """
        a = _abonnement("NLDD")
        stuk = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [stuk]}, feed_gewijzigd=False)

        s = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert resultaten == []
        assert client.zoekopdrachten == []

    @pytest.mark.asyncio
    async def test_changed_feed_runs_searches(self):
        a = _abonnement("NLDD")
        stuk = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [stuk]}, feed_gewijzigd=True)

        s = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert [r.zaak_nummer for r in resultaten] == ["2026D45065"]
        assert client.zoekopdrachten == ['"NLDD"']

    @pytest.mark.asyncio
    async def test_broken_klopper_still_searches(self):
        """Een mislukte optimalisatie mag geen gemiste alert opleveren."""
        a = _abonnement("NLDD")
        stuk = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [stuk]}, feed_gewijzigd=None)

        s = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        resultaten = await s.fetch_items(client=client, since=None, limit=10)

        assert [r.zaak_nummer for r in resultaten] == ["2026D45065"]


class TestPollRitme:
    """Het poll-interval volgt wanneer kamerstukken verschijnen.

    De tijden zijn Europe/Amsterdam, niet UTC: de Tweede Kamer publiceert
    op Nederlandse kantooruren, en in de zomer scheelt dat twee uur.
    """

    def _settings(self):
        from bouwmeester.core.config import Settings

        return Settings()

    def test_kantooruren_is_snelst(self):
        from bouwmeester.worker import _tkconv_interval

        s = self._settings()
        # 11:00 zat in de meting op 113 stukken.
        nu = datetime(2026, 9, 22, 11, 0, tzinfo=_AMSTERDAM)
        assert _tkconv_interval(s, nu) == 120

    def test_avond_is_trager_maar_niet_uit(self):
        from bouwmeester.worker import _tkconv_interval

        s = self._settings()
        # De avondstaart is dun (2 stukken in acht dagen) maar niet leeg,
        # dus een stuk van 20:00 wacht niet tot de ochtend.
        nu = datetime(2026, 9, 22, 20, 0, tzinfo=_AMSTERDAM)
        assert _tkconv_interval(s, nu) == 600

    def test_nacht_is_traagst(self):
        from bouwmeester.worker import _tkconv_interval

        s = self._settings()
        nu = datetime(2026, 9, 22, 3, 0, tzinfo=_AMSTERDAM)
        assert _tkconv_interval(s, nu) == 3600

    def test_grenzen(self):
        from bouwmeester.worker import _tkconv_interval

        s = self._settings()
        d = datetime(2026, 9, 22, tzinfo=_AMSTERDAM)
        assert _tkconv_interval(s, d.replace(hour=8)) == 120
        assert _tkconv_interval(s, d.replace(hour=17)) == 120
        assert _tkconv_interval(s, d.replace(hour=18)) == 600
        assert _tkconv_interval(s, d.replace(hour=22)) == 600
        assert _tkconv_interval(s, d.replace(hour=23)) == 3600
        assert _tkconv_interval(s, d.replace(hour=7)) == 3600


class TestEtagCache:
    """De ETag-cache moet een ronde overleven.

    De import-service bouwt elke ronde een verse client. Stond de cache op
    de instantie, dan was hij altijd leeg: geen `If-None-Match`, dus 200
    met de volle body in plaats van een 304 van 0 bytes, en het
    twee-minuten-ritme zou 360 volledige GET's per dag doen op een feed van
    een halve megabyte.
    """

    def setup_method(self):
        reset_etag_cache()

    def teardown_method(self):
        reset_etag_cache()

    def test_survives_a_new_client(self):
        c1 = TkconvClient()
        c1._etags["https://berthub.eu/tkconv/index.xml"] = '"abc"'

        c2 = TkconvClient()

        assert c2._etags.get("https://berthub.eu/tkconv/index.xml") == '"abc"'

    def test_survives_a_new_strategy_round(self):
        # Precies wat _import_type doet: per ronde een verse client.
        s = TkconvSearchStrategy()
        s.build_client()._etags["feed"] = '"v1"'

        assert s.build_client()._etags.get("feed") == '"v1"'

    def test_reset_empties_it(self):
        TkconvClient()._etags["feed"] = '"v1"'
        reset_etag_cache()
        assert TkconvClient()._etags == {}


class TestWatermerk:
    """Het watermerk moet een ronde overleven en opschuiven.

    De import-service bouwt elke ronde een verse strategie en geeft altijd
    `since=None` mee. Stond het watermerk op de instantie, dan was de
    drempel elke ronde "nu" — en een stuk uit de feed is per definitie al
    gepubliceerd, dus altijd ouder. De feature importeerde daardoor
    structureel nul stukken.
    """

    def setup_method(self):
        reset_watermerk()
        reset_etag_cache()

    def teardown_method(self):
        reset_watermerk()
        reset_etag_cache()

    @pytest.mark.asyncio
    async def test_recent_item_is_imported_with_since_none(self):
        """Het geval uit productie: since=None, stuk van 30 seconden oud."""
        a = _abonnement("NLDD")
        net = _item("2026D45065", datetime.now(UTC) - timedelta(seconds=30))
        client = _FakeClient({'"NLDD"': [net]})

        # Eerste ronde zet het watermerk op nu; dit stuk is ouder.
        s1 = TkconvSearchStrategy(abonnementen=[a])
        eerste = await s1.fetch_items(client=client, since=None, limit=100)
        assert eerste == []

        # Tweede ronde, verse strategie, stuk dat ná het watermerk komt.
        later = _item("2026D45099", datetime.now(UTC) + timedelta(seconds=5))
        client2 = _FakeClient({'"NLDD"': [later]})
        s2 = TkconvSearchStrategy(abonnementen=[a])
        tweede = await s2.fetch_items(client=client2, since=None, limit=100)

        assert [r.zaak_nummer for r in tweede] == ["2026D45099"]

    @pytest.mark.asyncio
    async def test_watermark_survives_a_new_strategy(self):
        a = _abonnement("NLDD")
        stuk = _item("2026D45065", datetime(2026, 9, 21, 12, 0, tzinfo=UTC))

        s1 = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        await s1.fetch_items(
            client=_FakeClient({'"NLDD"': [stuk]}), since=None, limit=100
        )

        # Verse strategie: hetzelfde stuk mag niet nog eens langskomen.
        s2 = TkconvSearchStrategy(abonnementen=[a])
        opnieuw = await s2.fetch_items(
            client=_FakeClient({'"NLDD"': [stuk]}), since=None, limit=100
        )
        assert opnieuw == []

    @pytest.mark.asyncio
    async def test_empty_round_does_not_advance_the_watermark(self):
        """Een ronde zonder treffers mag niets overslaan."""
        a = _abonnement("NLDD")

        s1 = TkconvSearchStrategy(abonnementen=[a])
        await s1.fetch_items(client=_FakeClient({'"NLDD"': []}), since=None, limit=100)

        from bouwmeester.services.import_strategies import tkconv as mod

        eerste_watermerk = mod._WATERMERK

        s2 = TkconvSearchStrategy(abonnementen=[a])
        await s2.fetch_items(client=_FakeClient({'"NLDD"': []}), since=None, limit=100)

        assert mod._WATERMERK == eerste_watermerk

    @pytest.mark.asyncio
    async def test_limit_does_not_fetch_documents_it_discards(self):
        """Afkappen gebeurt vóór het ophalen, niet erna.

        Anders halen we documenten op bij Berts server die we weggooien.
        """
        a = _abonnement("NLDD")
        stukken = [
            _item(f"2026D{i:05d}", datetime(2026, 9, 21, 12, i, tzinfo=UTC))
            for i in range(5)
        ]
        client = _FakeClient({'"NLDD"': stukken})

        s = TkconvSearchStrategy(abonnementen=[a], importeer_backlog=True)
        r = await s.fetch_items(client=client, since=None, limit=2)

        assert len(r) == 2
        assert len(client.opgehaalde_documenten) == 2


class TestInhaalslag:
    """Een verse zoekterm haalt eenmalig op wat de feed draagt.

    Dat is meestal juist de aanleiding om de term toe te voegen: je zag
    iets langskomen en wilt weten wat er verder over is verschenen. Daarna
    telt alleen nog wat nieuw is.
    """

    def setup_method(self):
        reset_watermerk()
        reset_etag_cache()

    def teardown_method(self):
        reset_watermerk()
        reset_etag_cache()

    @pytest.mark.asyncio
    async def test_verse_term_krijgt_de_hele_feed(self):
        vers = _abonnement("NLDD", ingehaald=False)
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        nieuwer = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [oud, nieuwer]})

        s = TkconvSearchStrategy(abonnementen=[vers])
        resultaten = await s.fetch_items(client=client, since=None, limit=100)

        # Beide stukken, ook die van een week geleden.
        assert {r.zaak_nummer for r in resultaten} == {"2026D38772", "2026D45065"}

    @pytest.mark.asyncio
    async def test_verse_term_meldt_zich_voor_een_samenvattend_bericht(self):
        """De stukken komen in `inhaalslag`, niet als losse alerts.

        Acht losse berichten bij het aanzetten van een term zou het kanaal
        overspoelen met stukken waar niemand om vroeg; één lijst zegt
        hetzelfde.
        """
        vers = _abonnement("NLDD", ingehaald=False)
        stuk = _item("2026D45065", datetime(2026, 9, 21, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [stuk]})

        s = TkconvSearchStrategy(abonnementen=[vers])
        await s.fetch_items(client=client, since=None, limit=100)

        # De strategie draagt wélke abonnementen vers zijn; welke
        # stukken erbij horen blijkt pas ná de idempotency-check in
        # de import-service, want een stuk dat al binnen was mag geen
        # treffer-loze vermelding in het inhaalbericht opleveren.
        assert s.verse_abonnementen == {vers.id}

    @pytest.mark.asyncio
    async def test_lopende_term_haalt_niet_opnieuw_in(self):
        lopend = _abonnement("NLDD", ingehaald=True)
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [oud]})

        s = TkconvSearchStrategy(abonnementen=[lopend])
        resultaten = await s.fetch_items(client=client, since=None, limit=100)

        assert resultaten == []
        assert s.verse_abonnementen == set()

    @pytest.mark.asyncio
    async def test_verse_en_lopende_term_op_hetzelfde_stuk(self):
        """Twee termen, verschillende leeftijd, één document.

        De verse term moet het stuk krijgen, de lopende niet. Zonder een
        drempel per abonnement zou het stuk voor allebei gelden of voor
        geen van beide.
        """
        vers = _abonnement("NLDD", ingehaald=False)
        lopend = _abonnement("RegelRecht", ingehaald=True)
        oud = _item("2026D38772", datetime(2026, 9, 15, tzinfo=UTC))
        client = _FakeClient({'"NLDD"': [oud], '"RegelRecht"': [oud]})

        s = TkconvSearchStrategy(abonnementen=[vers, lopend])
        resultaten = await s.fetch_items(client=client, since=None, limit=100)

        assert len(resultaten) == 1
        # Alleen de verse term is aan dit stuk gekoppeld.
        assert s.treffers["2026D38772"] == [vers.id]


class TestGeenStilVerlies:
    """De vier stil-verlies-bugs uit de review.

    Rode draad: toestand per *stuk* of per *query* bijhouden terwijl de
    beslissing per *abonnement* valt. Geen van deze bugs laat een spoor in
    de logs achter, dus ze horen hier vastgepind.
    """

    def setup_method(self):
        reset_watermerk()
        reset_etag_cache()

    def teardown_method(self):
        reset_watermerk()
        reset_etag_cache()

    @pytest.mark.asyncio
    async def test_afgekapte_ronde_verliest_niets(self):
        """Onder een limiet mag geen stuk permanent wegvallen.

        `search_many` sorteert nieuw-eerst. Kapte de lus daarop af, dan
        bleven de oudste stukken liggen én schoof het watermerk naar het
        nieuwste verwerkte stuk — waarmee de rest voorgoed onder de
        drempel viel. Gemeten: 3 van de 5 stukken verdwenen stil.
        """
        import bouwmeester.services.import_strategies.tkconv as mod

        a = _abonnement("NLDD")
        mod._WATERMERK = datetime(2026, 9, 1, tzinfo=UTC)
        stukken = [
            _item(f"2026D0000{i}", datetime(2026, 9, 10 + i, tzinfo=UTC))
            for i in range(5)
        ]

        gezien: set[str] = set()
        for _ in range(5):
            s = TkconvSearchStrategy(abonnementen=[a])
            r = await s.fetch_items(
                client=_FakeClient({'"NLDD"': stukken}), since=None, limit=2
            )
            gezien |= {x.zaak_nummer for x in r}

        assert gezien == {s.document_nummer for s in stukken}

    @pytest.mark.asyncio
    async def test_oudste_eerst_verwerken(self):
        """De volgorde is wat de afkapping veilig maakt."""
        import bouwmeester.services.import_strategies.tkconv as mod

        a = _abonnement("NLDD")
        mod._WATERMERK = datetime(2026, 9, 1, tzinfo=UTC)
        oud = _item("2026D00001", datetime(2026, 9, 10, tzinfo=UTC))
        nieuw = _item("2026D00002", datetime(2026, 9, 20, tzinfo=UTC))

        s = TkconvSearchStrategy(abonnementen=[a])
        r = await s.fetch_items(
            client=_FakeClient({'"NLDD"': [oud, nieuw]}), since=None, limit=1
        )

        # De oudste gaat eerst; de nieuwste blijft liggen en is de
        # volgende ronde nog steeds nieuwer dan het watermerk.
        assert [x.zaak_nummer for x in r] == ["2026D00001"]

    @pytest.mark.asyncio
    async def test_verse_term_omzeilt_de_etag_cache(self):
        """Een verse term moet de hele feed zien, niet alleen het nieuwe.

        De ETag-cache heeft de query als sleutel en weet niets van wie er
        zoekt. Had de poller die term al eens gedaan, dan gaf de volgende
        ronde 304 met een lege lijst — en kreeg een nieuw abonnement op
        diezelfde term zijn inhaalslag nooit.
        """
        vers = _abonnement("NLDD", ingehaald=False)
        lopend = _abonnement("RegelRecht", ingehaald=True)
        client = _FakeClient(
            {
                '"NLDD"': [_item("2026D00001", datetime(2026, 9, 15, tzinfo=UTC))],
                '"RegelRecht"': [
                    _item("2026D00002", datetime(2026, 9, 15, tzinfo=UTC))
                ],
            }
        )

        s = TkconvSearchStrategy(abonnementen=[vers, lopend])
        await s.fetch_items(client=client, since=None, limit=10)

        # Alleen de verse term omzeilt de cache; de lopende niet, want die
        # heeft juist baat bij een goedkope 304.
        assert client.cache_omzeild == ['"NLDD"']

    @pytest.mark.asyncio
    async def test_verse_term_dooft_andermans_alert_niet(self):
        """Eén verse term mag de losse alert van anderen niet onderdrukken.

        De oude check was per stuk: stond het document in iemands
        inhaalslag, dan kreeg niemand een losse alert. Het
        inhaalslag-bericht gaat alleen naar de scope van die ene term, dus
        de andere abonnees kregen helemaal niets.
        """
        import bouwmeester.services.import_strategies.tkconv as mod

        mod._WATERMERK = datetime(2026, 9, 1, tzinfo=UTC)
        lopend = _abonnement("RegelRecht", ingehaald=True)
        vers = _abonnement("NLDD", ingehaald=False)
        stuk = _item("2026D00222", datetime(2026, 9, 21, tzinfo=UTC))

        s = TkconvSearchStrategy(abonnementen=[lopend, vers])
        await s.fetch_items(
            client=_FakeClient({'"RegelRecht"': [stuk], '"NLDD"': [stuk]}),
            since=None,
            limit=10,
        )

        ids = s.treffers["2026D00222"]
        assert len(ids) == 2, "beide abonnementen horen gekoppeld te zijn"
        inhaal = [x for x in ids if x in s.verse_abonnementen]
        assert len(inhaal) == 1, "alleen de verse term doet een inhaalslag"
        # De import-service leidt hieruit af dat er nog een losse alert moet.
        assert len(inhaal) < len(ids)

    @pytest.mark.asyncio
    async def test_verse_abonnementen_draagt_ids_geen_stukken(self):
        """Welke stukken erbij horen blijkt pas ná de idempotency-check.

        Zou de strategie documentnummers bijhouden, dan zou een stuk dat
        al via een andere term binnen was in het inhaalbericht belanden
        zonder dat er ooit een treffer-rij voor is aangemaakt — en
        `ingehaald_op` werd dan gezet voor een term die zijn treffers
        nooit kreeg.
        """
        vers = _abonnement("NLDD", ingehaald=False)
        s = TkconvSearchStrategy(abonnementen=[vers])
        await s.fetch_items(
            client=_FakeClient(
                {'"NLDD"': [_item("2026D00001", datetime(2026, 9, 15, tzinfo=UTC))]}
            ),
            since=None,
            limit=10,
        )
        assert s.verse_abonnementen == {vers.id}


class TestDocumentGrens:
    """`getraw` kent geen bovengrens, de container wel.

    Op 23 september haalde de import een stuk van 128 MB op (2026D43577).
    Dat kwam als bytes binnen en ging als string door de PDF-parser, wat de
    pod herhaaldelijk OOMKilled opleverde. Omdat `markeer_ingehaald` pas na
    de hele ronde draait, begon elke volgende ronde opnieuw met dezelfde
    stukken.
    """

    @pytest.mark.asyncio
    async def test_haalt_niets_op_als_de_omvang_al_is_aangekondigd(self):
        """Een aangekondigde omvang boven de grens kost geen byte geheugen.

        De assertie telt wat er gelezen is en niet wat er terugkomt: op de
        oude code kwam er ook `None` uit, want de PDF-parser struikelt over
        een body van enkel x-en. Dat maakte de test groen terwijl de 128 MB
        wel degelijk binnen was gehaald. Wat we willen weten is of het
        geheugen geraakt wordt, dus meten we de bytes.
        """
        gelezen = 0

        async def body():
            nonlocal gelezen
            # Vier kleine blokken. De aangekondigde content-length doet het
            # werk, dus de blokken hoeven niet echt groot te zijn: we meten
            # of ze worden opgevraagd, niet hoeveel ze wegen.
            for _ in range(4):
                gelezen += 1
                yield b"x" * 1024

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/pdf",
                    "content-length": str(MAX_DOCUMENT_BYTES + 1),
                },
                content=body(),
            )

        client = TkconvClient()
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        tekst, content_type = await client.fetch_document_text("2026D43577")

        assert tekst is None
        assert content_type == "application/pdf"
        # Geen enkel blok opgevraagd: de content-length was genoeg.
        assert gelezen == 0
        await client.close()

    @pytest.mark.asyncio
    async def test_breekt_af_als_de_omvang_pas_tijdens_het_lezen_blijkt(
        self, monkeypatch
    ):
        """Zonder content-length telt de stream zelf mee.

        Bij chunked encoding kondigt de server de omvang niet aan. De grens
        moet dan alsnog gelden, en wel tijdens het lezen: we stoppen zodra
        de teller erover gaat, niet pas als het hele stuk binnen is.
        """
        blokken = 0
        blok = 64 * 1024
        # De grens tijdelijk omlaag, zodat de test hem met kilobytes raakt
        # in plaats van met de 20 MB uit productie. Een test die echt 40 MB
        # alloceert wordt zelf OOM-gekilled in de container, en dan toetsen
        # we het geheugen van de testrunner in plaats van dat van de code.
        grens = 256 * 1024
        monkeypatch.setattr(tkconv_client, "MAX_DOCUMENT_BYTES", grens)

        async def body():
            nonlocal blokken
            # Genoeg blokken om de grens ruim te passeren. Een afbrekende
            # lezer vraagt er grens / blok + 1 op; een lezer zonder grens
            # vraagt ze alle 40.
            for _ in range(40):
                blokken += 1
                yield b"x" * blok

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=body(),
            )

        client = TkconvClient()
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        tekst, _ = await client.fetch_document_text("2026D43577")

        assert tekst is None
        # Afgebroken net over de grens, niet pas aan het eind van de stream.
        assert blokken <= grens // blok + 1
        await client.close()

    @pytest.mark.asyncio
    async def test_laat_een_gewoon_document_door(self):
        """De grens mag niet raken wat er normaal langskomt (45 KB tot 16 MB)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"Nederlandse Digitale Dienst",
            )

        client = TkconvClient()
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        tekst, content_type = await client.fetch_document_text("2026D45064")

        assert tekst is not None
        assert "Nederlandse Digitale Dienst" in tekst
        assert content_type == "text/plain"
        await client.close()
