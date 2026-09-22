"""Een stuk dat al bestaat moet alsnog aan nieuwe zoektermen koppelen.

Het geval uit productie, 22 september 2026: de startnotitie NLDD werd
gevonden door zowel "van wet naar digitale werking" als "regelrecht". Het
inhaalbericht noemde het stuk bij beide termen, maar beide tellers stonden
op 0 — de idempotency-check in `_process_item` keert terug vóór de stap
die de treffers vastlegt.

Gevolg was breder dan een verkeerd getal: een latere alert over dat stuk
noemt de term niet, en een wegklik telt er niet voor mee.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from bouwmeester.services.import_strategies.base import FetchedItem
from bouwmeester.services.import_strategies.tkconv import TkconvSearchStrategy
from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)


def _service() -> ParlementairImportService:
    """Een service met alleen wat deze test aanraakt."""
    svc = ParlementairImportService.__new__(ParlementairImportService)
    svc.abonnement_repo = SimpleNamespace(registreer_treffers=AsyncMock(return_value=1))
    svc._inhaalslag = {}
    return svc


def _fetched(nummer: str) -> FetchedItem:
    return FetchedItem(
        zaak_id=nummer,
        zaak_nummer=nummer,
        titel="Startnotitie Nederlandse Digitale Dienst",
        onderwerp="",
        bron="tweede_kamer",
    )


class TestBestaandStukKoppelen:
    @pytest.mark.asyncio
    async def test_treffers_worden_alsnog_vastgelegd(self):
        """Het geval uit productie: tweede term, zelfde stuk."""
        svc = _service()
        bestaand = SimpleNamespace(id=uuid4())
        strategy = TkconvSearchStrategy()
        abo_id = uuid4()
        strategy.treffers = {"2026D45065": [abo_id]}
        strategy.verse_abonnementen = set()

        await svc._koppel_aan_bestaand_item(bestaand, _fetched("2026D45065"), strategy)

        svc.abonnement_repo.registreer_treffers.assert_awaited_once_with(
            bestaand.id, [abo_id]
        )

    @pytest.mark.asyncio
    async def test_verse_term_krijgt_het_stuk_in_de_inhaalslag(self):
        """Ook een al bekend stuk hoort bij de week die een verse term ophaalt."""
        svc = _service()
        bestaand = SimpleNamespace(id=uuid4())
        strategy = TkconvSearchStrategy()
        vers = uuid4()
        strategy.treffers = {"2026D45065": [vers]}
        strategy.verse_abonnementen = {vers}

        await svc._koppel_aan_bestaand_item(bestaand, _fetched("2026D45065"), strategy)

        assert svc._inhaalslag[vers] == [bestaand.id]

    @pytest.mark.asyncio
    async def test_lopende_term_komt_niet_in_de_inhaalslag(self):
        svc = _service()
        bestaand = SimpleNamespace(id=uuid4())
        strategy = TkconvSearchStrategy()
        strategy.treffers = {"2026D45065": [uuid4()]}
        strategy.verse_abonnementen = set()

        await svc._koppel_aan_bestaand_item(bestaand, _fetched("2026D45065"), strategy)

        assert svc._inhaalslag == {}

    @pytest.mark.asyncio
    async def test_zonder_treffers_gebeurt_er_niets(self):
        svc = _service()
        strategy = TkconvSearchStrategy()
        strategy.treffers = {}
        strategy.verse_abonnementen = set()

        await svc._koppel_aan_bestaand_item(
            SimpleNamespace(id=uuid4()), _fetched("2026D99999"), strategy
        )

        svc.abonnement_repo.registreer_treffers.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_andere_strategie_wordt_overgeslagen(self):
        """Moties en kamervragen kennen geen abonnementen."""
        svc = _service()
        andere = SimpleNamespace(treffers={}, verse_abonnementen=set())

        await svc._koppel_aan_bestaand_item(
            SimpleNamespace(id=uuid4()), _fetched("2026D00001"), andere
        )

        svc.abonnement_repo.registreer_treffers.assert_not_awaited()
