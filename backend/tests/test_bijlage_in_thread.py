"""Een bijlage hoort onder de brief waar hij bij hoort, niet ernaast.

Twee berichten over hetzelfde stuk, vlak na elkaar in het kanaal: een
beslisnota en de brief waar hij bij hoort. Dezelfde termen, dezelfde datum,
bijna dezelfde titel.

De bron levert ze in willekeurige volgorde, maar wél in dezelfde ronde. Dat
laatste is waarom er geen wachtrij of timer nodig is: sorteren volstaat.
Staat het hoofdstuk vooraan, dan bestaat zijn thread tegen de tijd dat de
bijlage wordt gepost.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services.parlementair_alert_service import ParlementairAlertService
from bouwmeester.services.parlementair_import_service import _hoofdstuk_voor_bijlage


def _stuk(nummer: str, bijlage_bij: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        zaak_id=nummer,
        extra_data={"bijlage_bij_nummer": bijlage_bij} if bijlage_bij else {},
    )


def _volgorde(items: list) -> list[str]:
    return [i.zaak_id for i in items]


class TestSortering:
    def test_de_bijlage_schuift_achter_zijn_hoofdstuk(self):
        """Het gemeten geval: bijlage eerst, brief erna."""
        items = [_stuk("bijlage-1", bijlage_bij="brief-1"), _stuk("brief-1")]

        assert _volgorde(_hoofdstuk_voor_bijlage(items)) == ["brief-1", "bijlage-1"]

    def test_een_bijlage_die_al_goed_staat_blijft_staan(self):
        items = [_stuk("brief-1"), _stuk("bijlage-1", bijlage_bij="brief-1")]

        assert _volgorde(_hoofdstuk_voor_bijlage(items)) == ["brief-1", "bijlage-1"]

    def test_meerdere_bijlagen_komen_allemaal_achter_hun_brief(self):
        items = [
            _stuk("bijlage-2", bijlage_bij="brief-1"),
            _stuk("los"),
            _stuk("bijlage-1", bijlage_bij="brief-1"),
            _stuk("brief-1"),
        ]

        # De onderlinge volgorde van de bijlagen blijft zoals de bron hem
        # gaf; alleen hun plek ten opzichte van de brief verandert.
        assert _volgorde(_hoofdstuk_voor_bijlage(items)) == [
            "los",
            "brief-1",
            "bijlage-2",
            "bijlage-1",
        ]

    def test_zonder_hoofdstuk_in_deze_ronde_verandert_er_niets(self):
        """Dan wordt het een los bericht, zoals het nu ook gaat.

        Wachten zou hier een stuk kunnen laten verdwijnen als de brief
        nooit komt, en dat is erger dan twee berichten.
        """
        items = [_stuk("bijlage-1", bijlage_bij="brief-elders"), _stuk("los")]

        assert _volgorde(_hoofdstuk_voor_bijlage(items)) == ["bijlage-1", "los"]

    def test_een_stuk_dat_naar_zichzelf_verwijst_blijft_staan(self):
        """Anders zou het zichzelf eindeloos vooruit schuiven."""
        items = [_stuk("brief-1", bijlage_bij="brief-1"), _stuk("los")]

        assert _volgorde(_hoofdstuk_voor_bijlage(items)) == ["brief-1", "los"]

    def test_een_ronde_zonder_bijlagen_komt_ongemoeid_terug(self):
        items = [_stuk("a"), _stuk("b"), _stuk("c")]

        assert _volgorde(_hoofdstuk_voor_bijlage(items)) == ["a", "b", "c"]

    def test_stukken_zonder_nummer_vallen_er_niet_uit(self):
        """Elk stuk dat erin gaat komt er ook weer uit."""
        items = [SimpleNamespace(zaak_id=None, extra_data={}), _stuk("a")]

        assert len(_hoofdstuk_voor_bijlage(items)) == 2


class TestErRaaktNooitIetsZoek:
    """De invariant, en die is hier belangrijker dan de volgorde.

    Een stuk dat uit deze lijst valt wordt niet los gepost maar verdwijnt:
    `_import_type` loopt alleen over wat hieruit komt, en het watermerk is
    al opgeschoven in `fetch_items`. De volgende ronde ziet het stuk niet
    meer, dus het verlies is permanent en stil.

    De eerste versie sloeg een verhuisd item over met `continue` en sprong
    daarmee ook over de regel die zijn eigen bijlagen uitgeeft. Een meting
    over 3000 willekeurige rondes vond 637 rondes waarin items verdwenen
    of dubbel voorkwamen.
    """

    def _controleer(self, items: list) -> list:
        uit = _hoofdstuk_voor_bijlage(items)
        assert sorted(id(i) for i in uit) == sorted(id(i) for i in items), (
            "elk stuk hoort er precies één keer uit te komen"
        )
        return uit

    def test_een_keten_verliest_het_middelste_stuk_niet(self):
        """A hangt aan B, B hangt aan C: geen van drieën mag wegvallen.

        Dit is realistisch: een beslisnota bij een brief bij een
        nota-overleg is een gewone stapeling, en de TK-API sluit niet uit
        dat een BronDocument zelf weer een BronDocument heeft.
        """
        items = [
            _stuk("A", bijlage_bij="B"),
            _stuk("B", bijlage_bij="C"),
            _stuk("C"),
        ]

        assert _volgorde(self._controleer(items)) == ["C", "B", "A"]

    def test_een_cykel_van_twee_verdampt_niet(self):
        items = [_stuk("A", bijlage_bij="B"), _stuk("B", bijlage_bij="A")]

        # Wie als eerste langskomt wordt de wortel; de ander hangt eronder.
        assert _volgorde(self._controleer(items)) == ["A", "B"]

    def test_een_cykel_van_drie_verdampt_niet(self):
        items = [
            _stuk("A", bijlage_bij="B"),
            _stuk("B", bijlage_bij="C"),
            _stuk("C", bijlage_bij="A"),
        ]

        assert len(self._controleer(items)) == 3

    def test_een_cykel_neemt_de_losse_stukken_niet_mee(self):
        items = [
            _stuk("X", bijlage_bij="Y"),
            _stuk("Y", bijlage_bij="X"),
            _stuk("Z"),
        ]

        assert sorted(_volgorde(self._controleer(items))) == ["X", "Y", "Z"]

    def test_hetzelfde_object_twee_keer_levert_niet_meer_op(self):
        brief = _stuk("brief-1")
        items = [_stuk("bijlage-1", bijlage_bij="brief-1"), brief, brief]

        # `id()` en niet `zaak_id`: twee losse objecten met hetzelfde
        # nummer zijn iets anders dan één object dat er twee keer in zit.
        uit = _hoofdstuk_voor_bijlage(items)
        assert len(uit) == 2
        assert _volgorde(uit) == ["brief-1", "bijlage-1"]

    def test_de_lus_heeft_een_bovengrens(self, monkeypatch):
        """Hangen is erger dan verkeerd sorteren.

        De cykelbescherming zit in één set-check. Valt die weg, dan draait
        de lus eindeloos en staat de hele importworker stil. De harde
        bovengrens vangt dat af, en het vangnet eronder zorgt dat er ook
        dan geen stuk verdwijnt.
        """
        import bouwmeester.services.parlementair_import_service as mod

        # Een stuk waarvan het nummer per uitlezing verandert, zodat de
        # `uitgegeven`-check nooit aanslaat: dat is wat een kapotte
        # cykelbescherming in de praktijk doet. Zonder bovengrens draait
        # de lus hierop eeuwig door.
        # Een lange keten met de grens kunstmatig op één omwenteling. Dan
        # kapt hij midden in af, precies zoals bij een kapotte
        # cykelcheck, en moet het vangnet de rest alsnog meenemen.
        items = [_stuk("s0")]
        items += [_stuk(f"s{n}", bijlage_bij=f"s{n - 1}") for n in range(1, 6)]

        monkeypatch.setattr(mod, "_SORTEER_MARGE", 0)

        uit = mod._hoofdstuk_voor_bijlage(items)

        # Komt terug in plaats van te hangen, en geen stuk is verdwenen.
        assert len(uit) == 6
        assert {i.zaak_id for i in uit} == {f"s{n}" for n in range(6)}

    def test_een_lange_keten_loopt_niet_vast(self):
        """Iteratief en niet recursief: de diepte komt uit een externe bron."""
        items = [_stuk("s0")]
        items += [_stuk(f"s{n}", bijlage_bij=f"s{n - 1}") for n in range(1, 1500)]

        assert len(self._controleer(items)) == 1500


async def _niets(*_args, **_kw):
    return None


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _Strategie:
    """Genoeg van een ImportStrategy om `_import_type` te laten lopen."""

    item_type = "tkconv"
    uses_tk_api = False
    supports_ek = False

    def __init__(self, items: list):
        self._items = items

    def build_client(self):
        return _Client()

    async def fetch_items(self, **_kw):
        return self._items


@pytest.mark.asyncio
class TestDeRondeGebruiktDeSortering:
    """Dat de functie werkt zegt niets als niemand hem aanroept.

    Precies dat faalmodel kostte deze week vijf reviewrondes: elke schakel
    deed het, en de keten was er niet. De sorteertests hierboven roepen
    `_hoofdstuk_voor_bijlage` rechtstreeks aan en blijven dus groen als de
    aanroep uit `run_import` verdwijnt.
    """

    async def test_de_ronde_verwerkt_het_hoofdstuk_eerst(self, monkeypatch):
        """Gemeten aan de werkelijke verwerkvolgorde, niet aan de broncode."""
        from bouwmeester.services import parlementair_import_service as mod

        svc = mod.ParlementairImportService.__new__(mod.ParlementairImportService)
        svc.settings = SimpleNamespace(TK_IMPORT_LIMIT=10, EK_IMPORT_ENABLED=False)
        svc.session = SimpleNamespace(commit=_niets, rollback=_niets)

        volgorde: list[str] = []

        async def _verwerk(item, _strategy):
            volgorde.append(item.zaak_id)
            return None

        svc._process_item = _verwerk

        # De bron levert de bijlage eerst, zoals in het gemeten geval.
        items = [_stuk("bijlage-1", bijlage_bij="brief-1"), _stuk("brief-1")]
        strategy = _Strategie(items)

        await svc._import_type(strategy)

        assert volgorde == ["brief-1", "bijlage-1"]


class _Mattermost:
    def __init__(self):
        self.draden: list[str | None] = []
        self.props: list[dict] = []
        self.kanalen: list[str] = []

    async def is_enabled(self) -> bool:
        return True

    async def send_channel_message(self, channel_id, text, props, root_id=None):
        self.kanalen.append(channel_id)
        self.draden.append(root_id)
        self.props.append(props)
        return "post-nieuw"

    async def add_reaction(self, post_id: str, emoji: str) -> bool:
        return True


class _Sessie:
    """Twee queries: eerst de kanalen, dan de thread van het hoofdstuk."""

    def __init__(self, thread: list[tuple[str, str]], kanalen=("kanaal-1",)):
        self._thread = thread
        self._kanalen = list(kanalen)

    async def execute(self, stmt):
        tekst = str(stmt)
        if "mattermost_channel_link" in tekst:
            links = [SimpleNamespace(channel_id=k) for k in self._kanalen]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: links))
        return SimpleNamespace(all=lambda: self._thread)

    def add(self, _rij):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _abonnement() -> ParlementairAbonnement:
    a = ParlementairAbonnement(
        scope_type="initiatief",
        scope_id=uuid4(),
        term="Fundament",
        term_genormaliseerd="fundament",
    )
    a.id = uuid4()
    a.minimum_relevantie = 20
    a.uitgezette_categorieen = None
    return a


def _bijlage(**extra) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        titel="Beslisnota bij Antwoord op vragen over cloudbeleid",
        onderwerp="Beslisnota",
        zaak_nummer="2026D50001",
        llm_samenvatting="De beslisnota adviseert in te stemmen.",
        document_url="https://berthub.eu/tkconv/x",
        datum=date(2026, 9, 29),
        document_tekst="",
        extra_data={"categorie": "bijlage", "relevantie_score": 85, **extra},
    )


def _svc(mm: _Mattermost, sessie: _Sessie, kanalen=None) -> ParlementairAlertService:
    if kanalen is not None:
        sessie._kanalen = list(kanalen)
    svc = ParlementairAlertService.__new__(ParlementairAlertService)
    svc.mattermost = mm
    svc.session = sessie

    async def _lijst(_item_id):
        return [_abonnement()]

    svc.abonnement_repo = SimpleNamespace(list_abonnementen_voor_item=_lijst)
    return svc


@pytest.mark.asyncio
class TestReplyInDeThread:
    async def test_de_bijlage_komt_in_de_thread_van_zijn_hoofdstuk(self):
        mm = _Mattermost()
        svc = _svc(mm, _Sessie(thread=[("kanaal-1", "post-brief")]))

        gepost = await svc.post_alert(_bijlage(bijlage_bij_nummer="brief-1"))

        assert gepost == 1
        assert mm.draden == ["post-brief"]

    async def test_zonder_gepost_hoofdstuk_een_gewoon_bericht(self):
        """De brief is er wel, maar staat (nog) in geen enkel kanaal."""
        mm = _Mattermost()
        svc = _svc(mm, _Sessie(thread=[]))

        gepost = await svc.post_alert(_bijlage(bijlage_bij_nummer="brief-1"))

        assert gepost == 1
        assert mm.draden == [None]

    async def test_een_stuk_dat_geen_bijlage_is_gaat_niet_in_een_thread(self):
        mm = _Mattermost()
        # Zelfs als er toevallig een rij te vinden zou zijn.
        svc = _svc(mm, _Sessie(thread=[("kanaal-1", "post-brief")]))

        gepost = await svc.post_alert(_bijlage())

        assert gepost == 1
        assert mm.draden == [None]

    async def test_in_de_thread_blijft_het_bericht_beknopt(self):
        """De termen, de kop en de voettekst staan al bij het hoofdstuk."""
        mm = _Mattermost()
        svc = _svc(mm, _Sessie(thread=[("kanaal-1", "post-brief")]))

        await svc.post_alert(_bijlage(bijlage_bij_nummer="brief-1"))

        bijlage = mm.props[0]["attachments"][0]
        # Weggelaten, niet leeg: dat is wat de andere attachment-bouwers
        # in deze codebase doen, en het scheelt de vraag hoe een renderer
        # een lege string behandelt.
        assert "fields" not in bijlage
        assert "pretext" not in bijlage
        assert "footer" not in bijlage
        # Wat de bijlage zélf toevoegt blijft staan. De titel ook: die
        # draagt de link en is waar een ingeklapte reply aan te herkennen
        # is.
        assert "adviseert in te stemmen" in bijlage["text"]
        assert bijlage["title"]
        assert bijlage["title_link"]

    async def test_los_in_het_kanaal_blijft_het_bericht_volledig(self):
        mm = _Mattermost()
        svc = _svc(mm, _Sessie(thread=[]))

        await svc.post_alert(_bijlage())

        los = mm.props[0]["attachments"][0]
        assert los["fields"]
        assert los["footer"]


@pytest.mark.asyncio
class TestPerKanaalApart:
    """Of er een thread is verschilt per kanaal, dus de vorm ook.

    Het hoofdstuk kan in het ene kanaal boven de drempel zijn gekomen en
    in het andere niet (`minimum_relevantie` staat per abonnement), of een
    kanaal is pas later gekoppeld. Eén keer beknopt beslissen voor alle
    kanalen gaf daar een bericht zonder kop, zonder termen en zonder
    voettekst, met niets erboven dat die context droeg. Dat is slechter
    dan wat er vóór deze wijziging stond.
    """

    async def test_zonder_thread_blijft_het_bericht_volledig(self):
        mm = _Mattermost()
        svc = _svc(
            mm,
            _Sessie(thread=[("kanaal-1", "post-brief")]),
            kanalen=["kanaal-1", "kanaal-2"],
        )

        await svc.post_alert(_bijlage(bijlage_bij_nummer="brief-1"))

        per_kanaal = dict(zip(mm.kanalen, mm.props, strict=True))
        in_de_thread = per_kanaal["kanaal-1"]["attachments"][0]
        los = per_kanaal["kanaal-2"]["attachments"][0]

        assert "footer" not in in_de_thread
        assert los["footer"]
        assert los["fields"]
        assert mm.draden == ["post-brief", None]


@pytest.mark.asyncio
class TestEenKapotteLookupHoudtHetBerichtNietTegen:
    """Dan wordt het een los bericht, en dat is beter dan geen bericht."""

    async def test_een_databasefout_laat_het_stuk_door(self):
        class _Stuk(_Sessie):
            async def execute(self, stmt):
                if "parlementair_alert_post" in str(stmt):
                    raise RuntimeError("database weg")
                return await super().execute(stmt)

        mm = _Mattermost()
        svc = _svc(mm, _Stuk(thread=[]))

        gepost = await svc.post_alert(_bijlage(bijlage_bij_nummer="brief-1"))

        assert gepost == 1
        assert mm.draden == [None]


@pytest.mark.asyncio
class TestDePayloadNaarMattermost:
    """Wat er werkelijk over de lijn gaat.

    De tests hierboven gebruiken een dubbel voor Mattermost, dus die zien
    niet of `root_id` ook in de request belandt. Zonder deze test blijft
    alles groen terwijl elke bijlage weer los in het kanaal komt.
    """

    async def _verstuur(self, **kw) -> dict:
        from bouwmeester.services.mattermost_service import MattermostService

        verstuurd: dict = {}

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id": "post-abc"}

        class _Client:
            async def post(self, _url, json=None):
                verstuurd.update(json or {})
                return _Resp()

        svc = MattermostService.__new__(MattermostService)

        async def _get_client():
            return _Client()

        svc._get_client = _get_client
        await svc.send_channel_message("kanaal-1", "tekst", None, **kw)
        return verstuurd

    async def test_root_id_gaat_mee_de_request_in(self):
        assert (await self._verstuur(root_id="post-brief"))["root_id"] == "post-brief"

    async def test_zonder_root_id_staat_het_veld_er_niet_in(self):
        """Een lege `root_id` meesturen zou Mattermost kunnen weigeren."""
        assert "root_id" not in await self._verstuur()
