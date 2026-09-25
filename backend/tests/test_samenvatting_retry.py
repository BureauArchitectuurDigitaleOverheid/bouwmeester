"""Een mislukte samenvatting krijgt een tweede kans.

Waarom dit nodig bleek: op 24 en 25 september 2026 kwamen een kamerstuk
en een agenda zonder samenvatting in het kanaal, terwijl dezelfde prompt
handmatig in één keer een bruikbaar antwoord gaf. De oorzaak was niet te
achterhalen, want de logs bewaren te kort.

Een alert is eenmalig: mislukt de samenvatting, dan valt het bericht
terug op de titel en komt het stuk nooit meer langs. Dat is een andere
afweging dan bij een achtergrondtaak die vanzelf opnieuw draait.
"""

from bouwmeester.services.llm.base import BaseLLMService

ANTWOORD = (
    '{"samenvatting": "De commissie besluit over de startnotitie.", '
    '"relevantie_score": 85, "reden": "kern", "actie": ""}'
)


def _svc(antwoorden: list):
    """Een service die per aanroep het volgende item uit de lijst geeft.

    Een string wordt teruggegeven, een exception wordt opgeworpen.
    """

    class _Stub(BaseLLMService):
        def __init__(self):
            self.aanroepen = 0

        async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
            self.aanroepen += 1
            volgende = antwoorden[self.aanroepen - 1]
            if isinstance(volgende, Exception):
                raise volgende
            return volgende

    return _Stub()


async def _vat_samen(svc):
    return await svc.summarize_kamerstuk_alert(
        titel="Agenda procedurevergadering",
        onderwerp="Agenda procedurevergadering",
        document_tekst="Agendapunt 8 over de Digitale Dienst.",
        zoektermen=["Digitale Dienst"],
        categorie="vergadering_vooruit",
    )


class TestRetry:
    async def test_eerste_poging_slaagt_geen_tweede(self):
        svc = _svc([ANTWOORD])
        uit = await _vat_samen(svc)

        assert svc.aanroepen == 1
        assert uit.samenvatting == "De commissie besluit over de startnotitie."

    async def test_tweede_poging_redt_het(self):
        """Het geval waarvoor dit bestaat: een vluchtige fout."""
        svc = _svc([TimeoutError("CLI overschreed 120s"), ANTWOORD])
        uit = await _vat_samen(svc)

        assert svc.aanroepen == 2
        assert uit.samenvatting == "De commissie besluit over de startnotitie."
        assert uit.relevantie_score == 85

    async def test_twee_keer_mis_is_definitief(self):
        """Niet blijven proberen: de ronde mag niet blijven hangen."""
        svc = _svc([TimeoutError("weg"), TimeoutError("weer weg")])
        uit = await _vat_samen(svc)

        assert svc.aanroepen == 2
        assert uit.samenvatting == ""

    async def test_de_reden_noemt_het_soort_fout(self):
        """Zonder dit is in de logs niet te zien wát er misging.

        Dat was precies het probleem: de logregel zei "samenvatting
        mislukt" en verder niets, en de logs waren weg voordat iemand
        keek.
        """
        svc = _svc([RuntimeError("stuk"), RuntimeError("stuk")])
        uit = await _vat_samen(svc)

        assert "RuntimeError" in uit.reden

    async def test_het_stuk_wordt_niet_verzwegen(self):
        """Een lege samenvatting is geen reden om niets te posten."""
        svc = _svc([RuntimeError("stuk"), RuntimeError("stuk")])
        uit = await _vat_samen(svc)

        # 50 = middenmoot, zodat het stuk boven de standaarddrempel blijft.
        assert uit.relevantie_score == 50

    async def test_onzin_antwoord_telt_als_mislukking(self):
        """Geen JSON is net zo onbruikbaar als een exception."""
        svc = _svc(["dit is geen json", ANTWOORD])
        uit = await _vat_samen(svc)

        assert svc.aanroepen == 2
        assert uit.samenvatting == "De commissie besluit over de startnotitie."
