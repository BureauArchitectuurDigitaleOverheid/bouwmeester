"""Eén stuk levert hooguit één bericht per ronde op.

Het geval, 24 september 2026: hetzelfde kamerstuk verscheen twee keer in
`~in-de-kamer`, zeven minuten na elkaar. Een los alert en een
inhaalbericht.

Dat gebeurt wanneer een stuk via meerdere termen binnenkomt en er één van
vers is. De bestaande termen krijgen hun losse alert (want een verse term
mag die niet doven), de verse term zijn eenmalige inhaalslag. Beide
keuzes zijn op zichzelf goed; alleen de uitkomst samen is dat niet.

De poort zit vlak voor het posten, niet bij het verzamelen: pas daar staat
vast wat er werkelijk gepost is. Dat onderscheid is de hele reden dat deze
tests `_post_inhaalslag` echt aanroepen. Een eerdere versie herschreef de
filterregel in de testbody en bleef groen met de poort volledig
verwijderd.
"""

import uuid
from types import SimpleNamespace

import pytest

from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)


class _Repo:
    """Onthoudt welke abonnementen als ingehaald zijn gemarkeerd."""

    def __init__(self):
        self.gemarkeerd: list = []

    async def get(self, abonnement_id):
        return SimpleNamespace(
            id=abonnement_id,
            scope_type="initiatief",
            scope_id=SCOPE_ID,
            term="rijkscloud",
        )

    async def markeer_ingehaald(self, ids):
        self.gemarkeerd.extend(ids)


class _Sessie:
    def __init__(self, items: dict):
        self._items = items

    async def get(self, _model, iid):
        return self._items.get(iid)

    async def commit(self):
        pass

    async def rollback(self):
        pass


SCOPE_ID = uuid.uuid4()


def _item(iid):
    return SimpleNamespace(id=iid, zaak_nummer=str(iid)[:8], extra_data={})


def _svc(items: dict) -> ParlementairImportService:
    svc = ParlementairImportService.__new__(ParlementairImportService)
    svc._gepost_deze_ronde = set()
    svc.session = _Sessie(items)
    svc.abonnement_repo = _Repo()
    svc.gepost_aan = []

    async def _beoordeel(_item, _abos):
        return None

    svc._beoordeel = _beoordeel
    return svc


@pytest.fixture
def geposte(monkeypatch):
    """Vang af wat `post_inhaalslag` te zien krijgt."""
    gezien: list = []

    class _Alert:
        def __init__(self, _session):
            pass

        async def post_inhaalslag(self, _abos, items):
            gezien.append([i.id for i in items])
            return 1

    monkeypatch.setattr(
        "bouwmeester.services.parlementair_alert_service.ParlementairAlertService",
        _Alert,
    )
    return gezien


class TestDedupPoort:
    async def test_al_gepost_stuk_valt_uit_de_inhaalslag(self, geposte):
        """De kern: hetzelfde stuk niet twee keer in hetzelfde kanaal."""
        gepost, vers = uuid.uuid4(), uuid.uuid4()
        abo = uuid.uuid4()
        svc = _svc({gepost: _item(gepost), vers: _item(vers)})
        svc._gepost_deze_ronde.add(gepost)

        await svc._post_inhaalslag({abo: [gepost, vers]})

        assert geposte == [[vers]]

    async def test_zonder_overlap_gaat_alles_mee(self, geposte):
        a, b = uuid.uuid4(), uuid.uuid4()
        svc = _svc({a: _item(a), b: _item(b)})

        await svc._post_inhaalslag({uuid.uuid4(): [a, b]})

        assert geposte == [[a, b]]

    async def test_alles_al_gepost_geeft_geen_bericht(self, geposte):
        """Een tweede bericht met dezelfde stukken voegt niets toe."""
        a = uuid.uuid4()
        svc = _svc({a: _item(a)})
        svc._gepost_deze_ronde.add(a)

        await svc._post_inhaalslag({uuid.uuid4(): [a]})

        assert geposte == []

    async def test_markeert_ook_als_alles_wegvalt(self, geposte):
        """Anders doet de term zijn inhaalslag elke ronde opnieuw."""
        a = uuid.uuid4()
        abo = uuid.uuid4()
        svc = _svc({a: _item(a)})
        svc._gepost_deze_ronde.add(a)

        await svc._post_inhaalslag({abo: [a]})

        assert svc.abonnement_repo.gemarkeerd == [abo]


class TestAlleenEchtGeposteStukkenTellen:
    """Een alert die niets toonde mag de inhaalslag niet blokkeren.

    Dit was de regressie die deze poort introduceerde: het stuk werd
    onvoorwaardelijk als "gepost" gemarkeerd, ook wanneer `post_alert`
    nul kanalen haalde omdat het onder `minimum_relevantie` bleef. De
    verse term, die hem wél had getoond, sloeg hem daarna over. Met
    `markeer_ingehaald` erbij was dat verlies permanent.
    """

    async def test_niet_gepost_stuk_blijft_in_de_inhaalslag(self, geposte):
        a = uuid.uuid4()
        svc = _svc({a: _item(a)})
        # `_alert_kamerstuk` gaf 0 terug: onder de drempel, geen kanaal,
        # of een fout. De aanroeper voegt dan niets toe aan de set.
        assert a not in svc._gepost_deze_ronde

        await svc._post_inhaalslag({uuid.uuid4(): [a]})

        assert geposte == [[a]]

    def test_de_aanroeper_kijkt_naar_de_uitkomst(self):
        """Bindt de lus aan de returnwaarde van `_alert_kamerstuk`.

        Een gedragstest hierop vraagt de hele importronde met mocks;
        deze assertie dekt precies de regel die de regressie veroorzaakte.
        """
        import inspect

        bron = inspect.getsource(ParlementairImportService._import_type)
        assert "if await self._alert_kamerstuk(item_id):" in bron, (
            "alleen een alert die werkelijk iets postte mag het stuk uit "
            "de inhaalslag houden"
        )


class TestMarkeerIngehaaldBlijftLopen:
    """De markering hoort niet af te hangen van wat er te posten viel.

    Staat `ingehaald_op` op NULL, dan doet de term zijn inhaalslag de
    volgende ronde opnieuw.
    """

    def test_volgorde_in_de_code(self):
        import inspect

        bron = inspect.getsource(ParlementairImportService._post_inhaalslag)
        markeer = bron.index("markeer_ingehaald")
        posten = bron.index("post_inhaalslag(abonnementen")

        assert markeer < posten, (
            "markeer_ingehaald moet vóór het posten staan, anders herhaalt "
            "een mislukte of lege inhaalslag zich elke ronde"
        )
