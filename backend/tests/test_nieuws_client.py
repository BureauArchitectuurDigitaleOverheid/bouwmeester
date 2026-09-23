"""Tests voor het lezen van nieuws-RSS.

De feeds dragen geen volledige artikeltekst (gemeten 23 september 2026:
teaser van 131 tekens bij iBestuur, 345 bij Binnenlands Bestuur, geen
`content:encoded` bij beide). Zoeken gebeurt daarom in titel plus teaser,
en deze tests leggen vast dat die twee ook echt allebei meetellen.
"""

from bouwmeester.services.nieuws_client import (
    NieuwsItem,
    _schoon,
    parse_feed,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Het kanaal zelf</title>
  <item>
    <title><![CDATA[Nederlandse Digitale Dienst krijgt vorm]]></title>
    <link>https://example.org/a</link>
    <guid>https://example.org/a</guid>
    <description><![CDATA[<p>Het kabinet <b>meldt</b> dat de dienst start.</p>]]>
    </description>
    <pubDate>Wed, 23 Sep 2026 11:13:43 +0200</pubDate>
  </item>
  <item>
    <title>Iets heel anders</title>
    <link>https://example.org/b</link>
    <guid>https://example.org/b</guid>
    <description>Over bermbeheer.</description>
    <pubDate>Tue, 22 Sep 2026 09:00:00 +0200</pubDate>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Kanaal</title>
  <entry>
    <title>Soevereine overheidscloud beoordeeld</title>
    <link href="https://example.org/c"/>
    <id>tag:example.org,2026:c</id>
    <summary>Een samenvatting.</summary>
    <updated>2026-09-23T09:00:00Z</updated>
  </entry>
</feed>"""


class TestParseFeed:
    def test_leest_rss(self):
        items = parse_feed(RSS, "ibestuur")
        assert len(items) == 2
        assert items[0].titel == "Nederlandse Digitale Dienst krijgt vorm"
        assert items[0].link == "https://example.org/a"
        assert items[0].bron == "ibestuur"

    def test_de_titel_van_het_kanaal_telt_niet_mee(self):
        """Anders zou elke ronde een artikel 'Het kanaal zelf' opleveren."""
        titels = [i.titel for i in parse_feed(RSS, "x")]
        assert "Het kanaal zelf" not in titels

    def test_html_gaat_uit_de_teaser(self):
        item = parse_feed(RSS, "x")[0]
        assert "<p>" not in item.samenvatting
        assert "<b>" not in item.samenvatting
        assert item.samenvatting == "Het kabinet meldt dat de dienst start."

    def test_datum_uit_rss(self):
        item = parse_feed(RSS, "x")[0]
        assert item.gepubliceerd is not None
        assert item.gepubliceerd.year == 2026
        assert item.gepubliceerd.month == 9
        assert item.gepubliceerd.day == 23

    def test_leest_atom(self):
        """Niet elke bron levert RSS; de link zit daar in een attribuut."""
        items = parse_feed(ATOM, "x")
        assert len(items) == 1
        assert items[0].link == "https://example.org/c"
        assert items[0].gepubliceerd is not None

    def test_item_zonder_titel_valt_af(self):
        """Liever overslaan dan een alert zonder kop posten."""
        xml = "<rss><channel><item><link>https://x/1</link></item></channel></rss>"
        assert parse_feed(xml, "x") == []

    def test_lege_feed(self):
        assert parse_feed("<rss><channel></channel></rss>", "x") == []

    def test_onzin_breekt_niet(self):
        assert parse_feed("dit is geen xml", "x") == []


class TestDoorzoekbareTekst:
    def test_titel_en_teaser_tellen_allebei(self):
        """De term staat even vaak in de kop als in de eerste zin."""
        item = NieuwsItem(
            gid="1",
            titel="Kabinet kiest voor e-facturatie",
            samenvatting="De Nederlandse Digitale Dienst gaat dit uitwerken.",
            link="https://x/1",
            gepubliceerd=None,
            bron="x",
        )
        tekst = item.doorzoekbare_tekst.lower()
        assert "e-facturatie" in tekst
        assert "nederlandse digitale dienst" in tekst


class TestSchoon:
    def test_entiteiten(self):
        assert _schoon("Jansen &amp; Co") == "Jansen & Co"

    def test_witruimte(self):
        assert _schoon("veel    ruimte\n\nhier") == "veel ruimte hier"

    def test_leeg(self):
        assert _schoon(None) == ""
        assert _schoon("") == ""
