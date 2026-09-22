"""Tests voor de tkconv-client en de zoekterm-strategie.

De fixtures zijn echte RSS-vormen zoals de feed ze op 22 september 2026
leverde, met de documentnummers erin. Dat is bewust: de twee gevallen die
het ontwerp bepalen (een bijlage zonder zaak-koppeling, en een stuk dat
alleen in de body matcht) zijn allebei publieke kamerstukken.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services.import_strategies.tkconv import (
    TkconvSearchStrategy,
    reset_watermerk,
)
from bouwmeester.services.tkconv_client import (
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


def _abonnement(term: str, *, is_frase: bool = True) -> ParlementairAbonnement:
    a = ParlementairAbonnement(
        scope_type="initiatief",
        scope_id=uuid4(),
        term=term,
        term_genormaliseerd=ParlementairAbonnement.normaliseer(term),
        is_frase=is_frase,
    )
    a.id = uuid4()
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

    async def globale_feed_gewijzigd(self) -> bool | None:
        return self.feed_gewijzigd

    async def search(self, query: str) -> list[TkconvItem]:
        self.zoekopdrachten.append(query)
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
