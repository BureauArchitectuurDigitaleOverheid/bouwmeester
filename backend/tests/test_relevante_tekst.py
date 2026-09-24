"""De tag-extractie krijgt de passages, niet de voorpagina.

`build_extract_tags_prompt` kapt af op de eerste 10.000 tekens. Dat is bij
een verslag van een schriftelijk overleg (gemeten: 43.185 tekens voor
2026D45836) de voorpagina plus de inhoudsopgave, en dan moet het model
tags kiezen voor een stuk waarvan het het onderwerp nooit heeft gezien.

Het alert-pad deed dit al goed met `knip_rond_termen`; de tag-extractie
niet. Deze tests leggen vast dat beide paden nu dezelfde tekst zien.
"""

from types import SimpleNamespace
from uuid import uuid4

from bouwmeester.services.import_strategies.base import FetchedItem
from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)


def _svc() -> ParlementairImportService:
    return ParlementairImportService.__new__(ParlementairImportService)


def _item(tekst: str) -> FetchedItem:
    return FetchedItem(
        zaak_id="2026D45836",
        zaak_nummer="2026D45836",
        titel="Inbreng verslag schriftelijk overleg over cloudbeleid",
        onderwerp="",
        document_tekst=tekst,
    )


def _lang_document(term: str) -> str:
    """Een stuk waarin de term ver voorbij de promptlimiet valt."""
    return ("voorpagina en inhoudsopgave. " * 800) + f"Het gaat hier over {term}."


class TestRelevanteTekst:
    def test_knipt_rond_de_zoekterm(self):
        abo = SimpleNamespace(id=uuid4(), term="cloudbeleid")
        strategy = SimpleNamespace(
            treffers={"2026D45836": [abo.id]}, abonnementen=[abo]
        )
        tekst = _lang_document("cloudbeleid")

        uit = _svc()._relevante_tekst(_item(tekst), strategy)

        assert uit is not None
        assert "cloudbeleid" in uit
        # Ingekort, anders kapt de prompt hem alsnog vóór de term af.
        assert len(uit) < len(tekst)

    def test_zonder_treffers_blijft_de_tekst_heel(self):
        """Moties en kamervragen komen niet van een zoekterm."""
        strategy = SimpleNamespace(treffers={}, abonnementen=[])
        tekst = _lang_document("cloudbeleid")

        assert _svc()._relevante_tekst(_item(tekst), strategy) == tekst

    def test_strategie_zonder_treffers_attribuut(self):
        """De OData-strategieën dragen het veld niet; gedrag blijft gelijk."""
        strategy = SimpleNamespace()
        tekst = _lang_document("cloudbeleid")

        assert _svc()._relevante_tekst(_item(tekst), strategy) == tekst

    def test_leeg_document(self):
        strategy = SimpleNamespace(treffers={}, abonnementen=[])
        assert _svc()._relevante_tekst(_item(""), strategy) == ""

    def test_term_voorbij_de_promptlimiet_overleeft(self):
        """De kern van de bug, in één assert.

        Zonder knippen zou `document_tekst[:10000]` de term niet bevatten.
        """
        abo = SimpleNamespace(id=uuid4(), term="cloudbeleid")
        strategy = SimpleNamespace(
            treffers={"2026D45836": [abo.id]}, abonnementen=[abo]
        )
        tekst = _lang_document("cloudbeleid")
        assert "cloudbeleid" not in tekst[:10000]

        uit = _svc()._relevante_tekst(_item(tekst), strategy)

        assert "cloudbeleid" in uit[:10000]
