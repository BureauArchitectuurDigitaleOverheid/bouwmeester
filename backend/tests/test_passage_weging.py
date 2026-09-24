"""De passages worden gekozen op waarde, niet op volgorde.

Het geval, 2026D45836 (verslag van een schriftelijk overleg over
cloudbeleid, 43.185 tekens, 69 vraagtekens): de selectie nam simpelweg de
eerste vensters tot het budget op was. Bij dit soort stukken is dat
systematisch de verkeerde helft, want de inleiding en de inhoudsopgave
staan vooraan en de vragen staan achterin. Een lezer haalde met de hand
een passage uit het midden die het model nooit te zien kreeg.

Twee dingen moesten daarvoor veranderen: grote samengevoegde blokken
worden in stukken gehakt zodat ze apart kunnen meewegen, en de weging
kijkt naar vraagtekens en signaalwoorden in plaats van alleen naar de
positie in het document.
"""

from bouwmeester.services.zoekterm_passage import (
    MAX_TOTAAL,
    MAX_VENSTER,
    _begrensd,
    _waarde,
    knip_rond_termen,
)

VULLING = "Algemene inleidende tekst zonder veel inhoud. " * 60


class TestWaarde:
    def test_vraag_weegt_zwaarder_dan_een_kale_vermelding(self):
        """Even vaak de term, maar de een stelt een vraag en de ander niet."""
        kaal = "Hoofdstuk cloudbeleid. Bijlage cloudbeleid."
        met_vraag = "Welke rol speelt het cloudbeleid? Wat doet het cloudbeleid?"

        assert _waarde(met_vraag, (0, len(met_vraag)), ["cloudbeleid"]) > _waarde(
            kaal, (0, len(kaal)), ["cloudbeleid"]
        )

    def test_signaalwoorden_tellen_mee(self):
        zonder = _waarde("Er staat hier cloudbeleid in.", (0, 28), ["cloudbeleid"])
        met = _waarde(
            "Kan het kabinet het cloudbeleid toelichten?", (0, 42), ["cloudbeleid"]
        )
        assert met > zonder

    def test_zonder_term_geen_waarde_uit_de_term(self):
        assert _waarde("Een zin zonder de term.", (0, 23), ["cloudbeleid"]) == 0.0

    def test_losse_vraagtekens_tellen_niet(self):
        """Opmaakresten uit een docx zijn geen vragen.

        Zonder deze eis scoorde een reeks "? ? ?" hoger dan een echte
        kamervraag over de zoekterm.
        """
        rommel = "? " * 50
        echt = "Wat vindt het kabinet van het cloudbeleid?"
        assert _waarde(rommel, (0, len(rommel)), ["cloudbeleid"]) < _waarde(
            echt, (0, len(echt)), ["cloudbeleid"]
        )

    def test_vraag_zonder_de_zoekterm_telt_niet(self):
        """Dit gaat om passages over ónze term, niet om vraagdichtheid."""
        assert (
            _waarde(
                "Wanneer komt het kabinet met een reactie hierop?",
                (0, 47),
                ["cloudbeleid"],
            )
            == 0.0
        )


class TestBegrensd:
    def test_groot_venster_wordt_gehakt_niet_afgekapt(self):
        """Afkappen zou de tweede helft weggooien, hakken laat hem meewegen."""
        uit = _begrensd([(0, MAX_VENSTER * 3)])
        assert len(uit) == 3
        assert uit[0][0] == 0
        assert uit[-1][1] == MAX_VENSTER * 3

    def test_klein_venster_blijft_heel(self):
        assert _begrensd([(100, 300)]) == [(100, 300)]

    def test_de_stukken_sluiten_op_elkaar_aan(self):
        uit = _begrensd([(0, MAX_VENSTER * 2)])
        assert uit[0][1] == uit[1][0]


class TestKnipRondTermen:
    def test_passage_met_vragen_wint_van_de_inleiding(self):
        """De kern van de bug, in één test.

        De inleiding noemt de term vaak maar zegt niets; de passage
        verderop stelt de vraag. Bij selectie op volgorde won de
        inleiding.
        """
        inleiding = "Inhoudsopgave cloudbeleid. " * 120
        midden = VULLING
        vraag = (
            "Welke rol gaat de Digitale Dienst spelen om het cloudbeleid "
            "Rijksbreed af te dwingen? Kan het kabinet toelichten welke "
            "samenhang er is? Wanneer verwacht het kabinet resultaat? "
        ) * 3
        tekst = inleiding + midden + vraag + midden

        uit = knip_rond_termen(tekst, ["cloudbeleid"])

        assert "Digitale Dienst" in uit
        assert len(uit) <= MAX_TOTAAL

    def test_kop_wordt_niet_herhaald_als_passage(self):
        """Een venster dat in de kop valt leverde dezelfde tekst twee keer.

        De kop gaat er altijd los bij; een passage die eroverheen valt
        kostte bij 2026D45836 1.100 tekens aan een herhaalde voorpagina,
        ten koste van een passage met vragen.
        """
        # Een unieke zin aan het begin, zodat herhaling aantoonbaar is.
        kop_zin = "UNIEKE KOPZIN over cloudbeleid. "
        tekst = kop_zin + "vulling cloudbeleid. " * 500

        uit = knip_rond_termen(tekst, ["cloudbeleid"])

        assert uit.count("UNIEKE KOPZIN") == 1

    def test_kort_stuk_blijft_heel(self):
        tekst = "Een kort stuk over cloudbeleid."
        assert knip_rond_termen(tekst, ["cloudbeleid"]) == tekst

    def test_zonder_treffer_het_begin(self):
        tekst = "Lange tekst zonder de term. " * 400
        uit = knip_rond_termen(tekst, ["cloudbeleid"])
        assert uit == tekst[:MAX_TOTAAL]

    def test_blijft_onder_de_promptlimiet(self):
        tekst = ("cloudbeleid staat hier. " + VULLING) * 40
        assert len(knip_rond_termen(tekst, ["cloudbeleid"])) <= MAX_TOTAAL
