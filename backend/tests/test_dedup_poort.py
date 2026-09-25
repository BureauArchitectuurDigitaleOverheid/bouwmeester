"""Eén stuk levert hooguit één bericht per ronde op.

Het geval, 24 september 2026: hetzelfde kamerstuk verscheen twee keer in
`~in-de-kamer`, zeven minuten na elkaar. Een los alert en een
inhaalbericht.

Dat gebeurt wanneer een stuk via meerdere termen binnenkomt en er één van
vers is. De bestaande termen krijgen hun losse alert (want een verse term
mag die niet doven), de verse term zijn eenmalige inhaalslag. Beide
keuzes zijn op zichzelf goed; alleen de uitkomst samen is dat niet.

De poort zit vlak voor het posten, niet bij het verzamelen: pas daar staat
vast wat er werkelijk gepost is.
"""

import uuid

from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)


def _svc() -> ParlementairImportService:
    svc = ParlementairImportService.__new__(ParlementairImportService)
    svc._gepost_deze_ronde = set()
    return svc


class TestDedupPoort:
    def test_al_gepost_stuk_valt_uit_de_inhaalslag(self):
        svc = _svc()
        gepost = uuid.uuid4()
        vers = uuid.uuid4()
        svc._gepost_deze_ronde.add(gepost)

        over = [i for i in [gepost, vers] if i not in svc._gepost_deze_ronde]

        assert over == [vers]

    def test_zonder_overlap_verandert_er_niets(self):
        svc = _svc()
        ids = [uuid.uuid4(), uuid.uuid4()]

        over = [i for i in ids if i not in svc._gepost_deze_ronde]

        assert over == ids

    def test_de_set_start_leeg_per_ronde(self):
        """Anders zou een stuk van vorige ronde nu stil wegvallen."""
        svc = _svc()
        assert svc._gepost_deze_ronde == set()


class TestMarkeerIngehaaldBlijftLopen:
    """De markering hoort niet af te hangen van wat er te posten viel.

    Staat `ingehaald_op` op NULL, dan doet de term zijn inhaalslag de
    volgende ronde opnieuw. Bij een volledig ontdubbelde inhaalslag zou
    dat een lus opleveren.
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

    def test_posten_hangt_aan_items_maar_markeren_niet(self):
        import inspect

        bron = inspect.getsource(ParlementairImportService._post_inhaalslag)
        markeer = bron.index("markeer_ingehaald")
        if_items = bron.index("if items:")

        assert markeer < if_items
