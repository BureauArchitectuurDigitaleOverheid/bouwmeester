"""Tests voor het matchen van zoektermen tegen nieuwsfeeds.

Twee dingen die hier anders zijn dan bij tkconv, en die allebei fout
kunnen gaan zonder dat iemand het merkt:

De eerste ronde importeert niets. Een feed draagt 150 artikelen, tot
maanden terug; die in één keer posten zou de feature openen met een reeks
berichten over oud nieuws. Dezelfde keuze als bij tkconv, en daar was het
watermerk precies de plek waar een bug de hele feature stil hield.

Zoeken gebeurt aan onze kant, in titel plus teaser. Dat is alles wat de
feeds dragen.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bouwmeester.services.import_strategies import nieuws as mod
from bouwmeester.services.import_strategies.nieuws import NieuwsStrategy
from bouwmeester.services.nieuws_client import NieuwsClient, NieuwsItem


def _abo(term: str, actief: bool = True):
    return SimpleNamespace(
        id=uuid4(),
        term=term,
        term_genormaliseerd=term.lower(),
        actief=actief,
    )


def _artikel(titel: str, teaser: str = "", dagen_terug: int = 0, gid: str = ""):
    return NieuwsItem(
        gid=gid or titel,
        titel=titel,
        samenvatting=teaser,
        link=f"https://example.org/{abs(hash(titel)) % 1000}",
        gepubliceerd=datetime(2026, 9, 23 - dagen_terug, 10, 0, tzinfo=UTC),
        bron="iBestuur",
    )


class _VasteClient(NieuwsClient):
    """Levert een vaste lijst in plaats van een echte feed."""

    def __init__(self, artikelen):
        super().__init__(etags={})
        self._artikelen = artikelen

    async def haal(self, url: str, bron: str):
        return self._artikelen


@pytest.fixture(autouse=True)
def _schoon_watermerk():
    mod.reset_watermerk()
    yield
    mod.reset_watermerk()


def _strategie(abonnementen, artikelen):
    s = NieuwsStrategy()
    s.abonnementen = abonnementen
    s.bronnen = [SimpleNamespace(naam="iBestuur", feed_url="https://x/feed")]
    return s, _VasteClient(artikelen)


class TestEersteRonde:
    async def test_importeert_niets(self):
        """Anders opent de feature met 150 artikelen oud nieuws."""
        s, client = _strategie(
            [_abo("Nederlandse Digitale Dienst")],
            [_artikel("Nederlandse Digitale Dienst krijgt vorm", dagen_terug=5)],
        )
        assert await s.fetch_items(client=client, since=None, limit=50) == []

    async def test_zet_wel_het_watermerk(self):
        """Zonder dit blijft elke volgende ronde ook leeg."""
        s, client = _strategie(
            [_abo("Nederlandse Digitale Dienst")],
            [_artikel("Nederlandse Digitale Dienst krijgt vorm", dagen_terug=5)],
        )
        await s.fetch_items(client=client, since=None, limit=50)
        assert mod._WATERMERK is not None


class TestTweedeRonde:
    async def test_nieuw_artikel_komt_door(self):
        oud = _artikel("Oud bericht over NLDD", dagen_terug=5)
        s, client = _strategie([_abo("NLDD")], [oud])
        await s.fetch_items(client=client, since=None, limit=50)

        nieuw = _artikel("NLDD krijgt vorm", dagen_terug=0)
        s2, client2 = _strategie([_abo("NLDD")], [oud, nieuw])
        s2.abonnementen = s.abonnementen
        items = await s2.fetch_items(client=client2, since=None, limit=50)

        assert [i.titel for i in items] == ["NLDD krijgt vorm"]

    async def test_al_gezien_artikel_komt_niet_opnieuw(self):
        oud = _artikel("NLDD krijgt vorm", dagen_terug=1)
        s, client = _strategie([_abo("NLDD")], [oud])
        await s.fetch_items(client=client, since=None, limit=50)

        s2, client2 = _strategie(s.abonnementen, [oud])
        assert await s2.fetch_items(client=client2, since=None, limit=50) == []


class TestMatchen:
    async def _match(self, abonnementen, artikelen):
        s, client = _strategie(abonnementen, artikelen)
        await s.fetch_items(client=client, since=None, limit=50)
        s2, client2 = _strategie(abonnementen, artikelen)
        # Verse artikelen zodat ze boven het watermerk liggen.
        vers = [
            _artikel(a.titel, a.samenvatting, dagen_terug=-1, gid=a.gid)
            for a in artikelen
        ]
        s2.bronnen = s.bronnen
        return await s2.fetch_items(client=_VasteClient(vers), since=None, limit=50)

    async def test_term_in_de_titel(self):
        items = await self._match(
            [_abo("Nederlandse Digitale Dienst")],
            [_artikel("Nederlandse Digitale Dienst krijgt vorm")],
        )
        assert len(items) == 1

    async def test_term_in_de_teaser(self):
        """De kop noemt het onderwerp niet altijd; de eerste zin wel."""
        items = await self._match(
            [_abo("RegelRecht")],
            [_artikel("Kabinet kiest voor e-facturatie", "RegelRecht werkt dit uit.")],
        )
        assert len(items) == 1

    async def test_hoofdletters_maken_niet_uit(self):
        items = await self._match(
            [_abo("digitale dienst")],
            [_artikel("Digitale Dienst krijgt vorm")],
        )
        assert len(items) == 1

    async def test_zonder_treffer_geen_item(self):
        items = await self._match(
            [_abo("RegelRecht")],
            [_artikel("Gemeente vernieuwt bermbeheer")],
        )
        assert items == []

    async def test_gepauzeerde_term_telt_niet(self):
        items = await self._match(
            [_abo("NLDD", actief=False)],
            [_artikel("NLDD krijgt vorm")],
        )
        assert items == []

    async def test_treffers_worden_vastgelegd(self):
        """`_process_item` heeft nodig welke term het artikel aandroeg."""
        abo = _abo("NLDD")
        s, client = _strategie([abo], [_artikel("Oud", dagen_terug=5)])
        await s.fetch_items(client=client, since=None, limit=50)

        vers = _artikel("NLDD krijgt vorm", dagen_terug=-1)
        s2, _ = _strategie([abo], [vers])
        await s2.fetch_items(client=_VasteClient([vers]), since=None, limit=50)

        assert s2.treffers[vers.gid] == [abo.id]


class TestVorm:
    async def test_categorie_en_bron_staan_erbij(self):
        abo = _abo("NLDD")
        s, client = _strategie([abo], [_artikel("Oud", dagen_terug=5)])
        await s.fetch_items(client=client, since=None, limit=50)

        vers = _artikel("NLDD krijgt vorm", "Een teaser.", dagen_terug=-1)
        s2, _ = _strategie([abo], [vers])
        items = await s2.fetch_items(client=_VasteClient([vers]), since=None, limit=50)

        item = items[0]
        assert item.extra_data["categorie"] == "nieuws"
        assert item.extra_data["publicatie"] == "iBestuur"
        # Het model krijgt niet meer tekst dan waarin gezocht is.
        assert "NLDD krijgt vorm" in item.document_tekst
        assert "Een teaser." in item.document_tekst
