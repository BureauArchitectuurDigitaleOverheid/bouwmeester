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

    async def is_enabled(self) -> bool:
        return True

    async def send_channel_message(self, channel_id, text, props, root_id=None):
        self.draden.append(root_id)
        self.props.append(props)
        return "post-nieuw"

    async def add_reaction(self, post_id: str, emoji: str) -> bool:
        return True


class _Sessie:
    """Twee queries: eerst de kanalen, dan de thread van het hoofdstuk."""

    def __init__(self, thread: list[tuple[str, str]]):
        self._thread = thread

    async def execute(self, stmt):
        tekst = str(stmt)
        if "mattermost_channel_link" in tekst:
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(
                    all=lambda: [SimpleNamespace(channel_id="kanaal-1")]
                )
            )
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


def _svc(mm: _Mattermost, sessie: _Sessie) -> ParlementairAlertService:
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
        assert bijlage["fields"] == []
        assert bijlage["pretext"] == ""
        assert bijlage["footer"] == ""
        # Wat de bijlage zélf toevoegt blijft staan.
        assert "adviseert in te stemmen" in bijlage["text"]
        assert bijlage["title"]

    async def test_los_in_het_kanaal_blijft_het_bericht_volledig(self):
        mm = _Mattermost()
        svc = _svc(mm, _Sessie(thread=[]))

        await svc.post_alert(_bijlage())

        los = mm.props[0]["attachments"][0]
        assert los["fields"]
        assert los["footer"]


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
