"""Een mislukte LLM-aanroep mag geen tekst opleveren die op inhoud lijkt.

Het geval uit productie, 24 september 2026. In `~in-de-kamer` stond als
samenvatting van een kamerstuk:

    Tag-extractie mislukt

Dat is de letterlijke terugvalwaarde van `extract_tags`. Hij landt in
`ParlementairItem.llm_samenvatting`, en dat veld is precies wat
`format_alert` als berichttekst post. Een interne status werd zo
gepresenteerd als iets dat iemand had geschreven.

Twee dingen gingen mis en ze moeten los blijven werken: de bron van de
tekst (hier weggenomen) en het vangnet bij het posten (voor stukken die
de oude waarde al in de database dragen).
"""

from types import SimpleNamespace
from uuid import uuid4

from bouwmeester.services.parlementair_alert_service import (
    _bruikbare_samenvatting,
)


def _item(**extra) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        titel="Inbreng verslag schriftelijk overleg over cloudbeleid",
        onderwerp="Verslag van een schriftelijk overleg over cloudbeleid",
        zaak_nummer="2026D45836",
        llm_samenvatting=extra.pop("samenvatting", ""),
        document_url="https://berthub.eu/tkconv/document.html?nummer=2026D45836",
        datum=None,
        extra_data=extra,
    )


class TestBruikbareSamenvatting:
    def test_echte_samenvatting_blijft(self):
        tekst = "De commissie vraagt het kabinet om een reactie op het cloudbeleid."
        assert _bruikbare_samenvatting(tekst) == tekst

    def test_foutmelding_wordt_leeg(self):
        """Precies de tekst die in productie in het kanaal stond."""
        assert _bruikbare_samenvatting("Tag-extractie mislukt") == ""

    def test_hoofdletters_maken_niet_uit(self):
        assert _bruikbare_samenvatting("tag-extractie mislukt") == ""
        assert _bruikbare_samenvatting("TAG-EXTRACTIE MISLUKT") == ""

    def test_punt_erachter_maakt_niet_uit(self):
        assert _bruikbare_samenvatting("Tag-extractie mislukt.") == ""

    def test_witruimte_eromheen(self):
        assert _bruikbare_samenvatting("  Tag-extractie mislukt  ") == ""

    def test_andere_bekende_foutmelding(self):
        assert _bruikbare_samenvatting("samenvatting mislukt") == ""

    def test_leeg_blijft_leeg(self):
        assert _bruikbare_samenvatting(None) == ""
        assert _bruikbare_samenvatting("") == ""

    def test_zin_die_de_woorden_bevat_blijft(self):
        """Alleen een exacte match telt.

        Een samenvatting die tóevallig over een mislukking gaat is nog
        steeds een samenvatting; wegfilteren op deelstring zou echte
        inhoud weggooien.
        """
        tekst = "De extractie mislukt volgens de commissie stelselmatig bij DUO."
        assert _bruikbare_samenvatting(tekst) == tekst


class TestAlertValtTerugOpHetOnderwerp:
    """Wat de lezer in plaats daarvan ziet."""

    def _svc(self):
        from bouwmeester.services.parlementair_alert_service import (
            ParlementairAlertService,
        )

        return ParlementairAlertService.__new__(ParlementairAlertService)

    def test_foutmelding_wordt_het_onderwerp(self):
        _, props = self._svc().format_alert(
            _item(samenvatting="Tag-extractie mislukt", relevantie_score=60),
            ['"cloudbeleid"'],
        )
        tekst = props["attachments"][0]["text"]
        assert "Tag-extractie mislukt" not in tekst
        assert "schriftelijk overleg over cloudbeleid" in tekst

    def test_echte_samenvatting_blijft_staan(self):
        _, props = self._svc().format_alert(
            _item(
                samenvatting="De commissie vraagt om een reactie.", relevantie_score=60
            ),
            ['"cloudbeleid"'],
        )
        assert "De commissie vraagt om een reactie." in props["attachments"][0]["text"]


class TestExtractTagsGeeftGeenFouttekst:
    """De bron van het probleem, weggenomen bij de terugval zelf."""

    async def test_mislukte_extractie_geeft_lege_samenvatting(self):
        from bouwmeester.services.llm.base import BaseLLMService

        class _Stuk(BaseLLMService):
            async def _complete(self, prompt: str) -> str:
                raise RuntimeError("model onbereikbaar")

        svc = _Stuk.__new__(_Stuk)
        result = await svc.extract_tags(
            titel="Een titel",
            onderwerp="Een onderwerp",
            document_tekst="Tekst",
            bestaande_tags=[],
        )

        assert result.samenvatting == ""
        assert result.matched_tags == []
