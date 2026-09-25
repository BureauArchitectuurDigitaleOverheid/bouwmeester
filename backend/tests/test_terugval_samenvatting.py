"""Wat er in het bericht komt als de samenvatting ontbreekt.

Het geval, 25 september 2026: een agenda van de commissie Digitale Zaken
kwam in het kanaal met als samenvatting letterlijk zijn eigen titel:

    AGENDA PROCEDUREVERGADERING · 30 september (over 5 dagen)
    📅 Agenda procedurevergadering commissie Digitale Zaken d.d. 30 september 2026
    Agenda procedurevergadering commissie Digitale Zaken d.d. 30 september 2026

De LLM-aanroep was mislukt, en de terugval pakte `item.onderwerp` — wat
bij een agenda woord voor woord de titel is. Het bericht zei daardoor
niets, terwijl het document wel degelijk vertelde dat er een
rondetafelgesprek over de oprichting van de dienst wordt voorbereid.
"""

from types import SimpleNamespace
from uuid import uuid4

from bouwmeester.services.parlementair_alert_service import _terugval

TITEL = "Agenda procedurevergadering commissie Digitale Zaken d.d. 30 september 2026"


def _item(**kw) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        titel=kw.pop("titel", TITEL),
        onderwerp=kw.pop("onderwerp", ""),
        document_tekst=kw.pop("document_tekst", ""),
    )


class TestTerugval:
    def test_onderwerp_wint_als_het_iets_toevoegt(self):
        uit = _terugval(
            _item(onderwerp="Verslag van een schriftelijk overleg over cloudbeleid")
        )
        assert uit == "Verslag van een schriftelijk overleg over cloudbeleid"

    def test_onderwerp_gelijk_aan_titel_valt_af(self):
        """De kern: twee keer dezelfde zin zegt niets."""
        uit = _terugval(
            _item(
                onderwerp=TITEL,
                document_tekst="Agendapunt 8: de commissie besluit over de "
                "Startnotitie Nederlandse Digitale Dienst.",
            )
        )
        assert uit != TITEL
        assert "Startnotitie" in uit

    def test_hoofdletters_maken_niet_uit(self):
        uit = _terugval(
            _item(
                onderwerp=TITEL.upper(),
                document_tekst="Iets anders uit het document.",
            )
        )
        assert uit == "Iets anders uit het document."

    def test_documenttekst_wordt_ingekort(self):
        uit = _terugval(_item(onderwerp=TITEL, document_tekst="woord " * 200))
        assert len(uit) <= 301
        assert uit.endswith("…")

    def test_witruimte_uit_de_documenttekst(self):
        """Een PDF levert regeleindes en dubbele spaties op."""
        uit = _terugval(
            _item(onderwerp=TITEL, document_tekst="Eerste regel.\n\n  Tweede   regel.")
        )
        assert uit == "Eerste regel. Tweede regel."

    def test_zonder_iets_bruikbaars_toch_het_onderwerp(self):
        """Een leeg bericht is erger dan een herhaalde titel."""
        assert _terugval(_item(onderwerp=TITEL, document_tekst="")) == TITEL

    def test_alles_leeg(self):
        assert _terugval(_item(titel="", onderwerp="", document_tekst="")) == ""


class TestInHetBericht:
    """Hetzelfde, maar dan zoals het in Mattermost terechtkomt."""

    def _tekst(self, **kw) -> str:
        from bouwmeester.services.parlementair_alert_service import (
            ParlementairAlertService,
        )

        svc = ParlementairAlertService.__new__(ParlementairAlertService)
        item = SimpleNamespace(
            id=uuid4(),
            titel=TITEL,
            onderwerp=kw.pop("onderwerp", TITEL),
            zaak_nummer="2026D46280",
            llm_samenvatting="",
            document_url="https://berthub.eu/tkconv/x",
            datum=None,
            document_tekst=kw.pop("document_tekst", ""),
            extra_data={"categorie": "vergadering_vooruit", "relevantie_score": 50},
        )
        _, props = svc.format_alert(item, ['"Digitale Dienst"'])
        return props["attachments"][0]["text"]

    def test_geen_dubbele_titel_meer(self):
        tekst = self._tekst(
            document_tekst=(
                "Agendapunt 8: de commissie besluit of de bijlage Startnotitie "
                "Nederlandse Digitale Dienst separaat wordt behandeld."
            )
        )
        assert TITEL not in tekst
        assert "Startnotitie" in tekst
