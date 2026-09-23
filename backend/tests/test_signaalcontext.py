"""De signaalcontext is het tweede tekstveld, naast de beschrijving.

Waarom twee velden: de beschrijving van een initiatief is publiek
(`/public/initiatief` geeft hem uit) en is voor een mens die wil weten wat
het initiatief doet. Wat een taalmodel nodig heeft om ruis te scheiden is
iets anders: welk woord is hier een metafoor, wat telt niet mee. Dat is
afstelling van een zoekmachine en hoort niet op een publieke pagina.

Het geval dat dit uitwees: "Het Fundament" is zowel de naam van een
project (Fundament, Soevereine Overheidscloud) als een staande Haagse
metafoor. Van 47 stukken in de eerste inhaalslag kwamen er 46 via die
term binnen, vrijwel allemaal de metafoor.
"""

from types import SimpleNamespace
from uuid import uuid4

from bouwmeester.services.llm.prompts import build_kamerstuk_alert_prompt


class TestPromptDraagtDeContext:
    def test_context_staat_in_de_prompt(self):
        prompt = build_kamerstuk_alert_prompt(
            titel="Nota over de toestand van 's Rijks Financiën",
            onderwerp="",
            document_tekst="Dit legt het fundament onder de begroting.",
            zoektermen=["Het Fundament"],
            signaalcontext=(
                "Fundament is de naam van een project (Soevereine "
                "Overheidscloud). Niet relevant: 'fundament' in figuurlijke zin."
            ),
        )

        assert "WAAR DIT DOSSIER OVER GAAT:" in prompt
        assert "Soevereine Overheidscloud" in prompt
        assert "figuurlijke zin" in prompt

    def test_context_gaat_voor_op_het_kamerstuk(self):
        """Eerst weten waar je naar kijkt, dan pas de tekst lezen."""
        prompt = build_kamerstuk_alert_prompt(
            titel="Een titel",
            onderwerp="",
            document_tekst="De tekst.",
            zoektermen=["term"],
            signaalcontext="De context.",
        )

        assert prompt.index("WAAR DIT DOSSIER OVER GAAT:") < prompt.index("KAMERSTUK:")

    def test_zonder_context_geen_lege_kop(self):
        """Een lege kop zou het model laten raden wat eronder hoort."""
        prompt = build_kamerstuk_alert_prompt(
            titel="Een titel",
            onderwerp="",
            document_tekst="De tekst.",
            zoektermen=["term"],
        )

        assert "WAAR DIT DOSSIER OVER GAAT:" not in prompt

    def test_model_hoort_de_context_zwaarder_te_wegen(self):
        """Zonder die instructie is de context decoratie.

        De zoekterm staat letterlijk in het stuk; alleen een expliciete
        opdracht laat het model daar tegenin gaan.
        """
        prompt = build_kamerstuk_alert_prompt(
            titel="Een titel",
            onderwerp="",
            document_tekst="De tekst.",
            zoektermen=["term"],
            signaalcontext="De context.",
        )

        assert "zwaarder wegen dan de zoekterm" in prompt


class TestOnderwerpKiestDeJuisteTekst:
    """De publieke beschrijving is de terugval, niet de eerste keus."""

    def _initiatief(self, beschrijving=None):
        return SimpleNamespace(id=uuid4(), naam="NLDD", beschrijving=beschrijving)

    def test_signaalcontext_wint_van_de_beschrijving(self):
        from bouwmeester.api.routes.parlementair_abonnement import _onderwerp_van

        onderwerp = _onderwerp_van(
            self._initiatief(beschrijving=None), "Wel dit, niet dat."
        )

        assert "Wel dit, niet dat." in onderwerp
        assert onderwerp.startswith("NLDD")

    def test_zonder_context_alleen_de_naam(self):
        from bouwmeester.api.routes.parlementair_abonnement import _onderwerp_van

        assert _onderwerp_van(self._initiatief(), None) == "NLDD"

    def test_lege_context_telt_als_geen_context(self):
        """Wie het veld leegmaakt bedoelt niet 'gebruik witruimte'."""
        from bouwmeester.api.routes.parlementair_abonnement import _onderwerp_van

        assert _onderwerp_van(self._initiatief(), "   \n  ") == "NLDD"
