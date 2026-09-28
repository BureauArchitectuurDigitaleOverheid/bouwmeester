"""Wegklikken telt mee, en de drempel snijdt op 20.

Twee dingen die tot 28 september 2026 niet werkten.

De kolom "Weggeklikt" stond sinds de bouw op nul en zou daar blijven
staan: `REACTIE_NIET_RELEVANT` bestond, `markeer_niet_relevant` bestond en
werkte, maar er was geen aanroeper. De oorzaak lag een laag dieper:
`send_channel_message` gaf een bool terug en gooide het post-id weg,
terwijl `_dispatch_reaction_added` juist op post-id zoekt.

En de drempel stond op 10. Een meting over 146 beoordeelde stukken liet
zien dat 20 stukken tussen 10 en 19 scoorden en geen van alle over het
dossier gingen.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.services.parlementair_alert_service import (
    REACTIE_NIET_RELEVANT,
    REACTIE_OPVOLGEN,
    ParlementairAlertService,
)


def _abonnement(**kw) -> ParlementairAbonnement:
    a = ParlementairAbonnement(
        scope_type="initiatief",
        scope_id=uuid4(),
        term=kw.pop("term", "Fundament"),
        term_genormaliseerd="fundament",
    )
    a.id = uuid4()
    a.minimum_relevantie = kw.pop("minimum_relevantie", 20)
    a.uitgezette_categorieen = None
    return a


def _item(**extra) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        titel="Rapport Onderzoek Dure Casuïstiek Jeugdwet",
        onderwerp="Onderzoek dure casuïstiek",
        zaak_nummer="2026D46887",
        llm_samenvatting="Gaat over jeugdzorg.",
        document_url="https://berthub.eu/tkconv/x",
        datum=date(2026, 9, 28),
        document_tekst="",
        extra_data=extra,
    )


class _Mattermost:
    """Vangt op wat er gepost en gereageerd wordt."""

    def __init__(self, post_id: str | None = "post123"):
        self._post_id = post_id
        self.reacties: list[tuple[str, str]] = []
        self.berichten: list[str] = []

    async def is_enabled(self) -> bool:
        return True

    async def send_channel_message(self, channel_id, text, props):
        self.berichten.append(channel_id)
        return self._post_id

    async def add_reaction(self, post_id: str, emoji: str) -> bool:
        self.reacties.append((post_id, emoji))
        return True


class _Sessie:
    def __init__(self):
        self.toegevoegd: list = []
        self.commits = 0

    def add(self, obj):
        self.toegevoegd.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _svc(mattermost=None, sessie=None) -> ParlementairAlertService:
    svc = ParlementairAlertService.__new__(ParlementairAlertService)
    svc.mattermost = mattermost or _Mattermost()
    svc.session = sessie or _Sessie()
    return svc


class TestDrempelOp20:
    """De grens ligt bij 20, en het jeugdzorgrapport zat er net onder."""

    def _haalt_drempel(self, score: int, drempel: int = 20) -> bool:
        from bouwmeester.services.parlementair_alert_service import _relevantie

        return _relevantie({"relevantie_score": score}) >= drempel

    def test_het_gemeten_geval_valt_nu_af(self):
        """Score 12: kwam door bij drempel 10, valt af bij 20."""
        assert self._haalt_drempel(12, drempel=10) is True
        assert self._haalt_drempel(12, drempel=20) is False

    def test_precies_op_de_grens_komt_door(self):
        assert self._haalt_drempel(20) is True

    def test_net_eronder_valt_af(self):
        assert self._haalt_drempel(19) is False

    def test_de_standaard_is_20(self):
        """Anders blijft elke nieuwe term op de oude, te lage waarde staan."""
        assert ParlementairAbonnement.minimum_relevantie.default.arg == 20


class TestPostOnthouden:
    """Zonder post-id kan een reactie nergens aan worden toegewezen."""

    async def test_post_id_wordt_vastgelegd(self):
        sessie = _Sessie()
        svc = _svc(sessie=sessie)
        item_id = uuid4()

        await svc._onthoud_post(item_id, "kanaal1", "post123")

        assert len(sessie.toegevoegd) == 1
        rij = sessie.toegevoegd[0]
        assert rij.parlementair_item_id == item_id
        assert rij.channel_id == "kanaal1"
        assert rij.post_id == "post123"

    async def test_reacties_worden_geplaatst(self):
        """Zonder zichtbare 'x' weet niemand dat wegklikken kan."""
        mm = _Mattermost()
        svc = _svc(mattermost=mm)

        await svc._onthoud_post(uuid4(), "kanaal1", "post123")

        emoji = [e for _, e in mm.reacties]
        assert REACTIE_NIET_RELEVANT in emoji
        assert REACTIE_OPVOLGEN in emoji

    async def test_mislukte_administratie_gooit_niet(self):
        """Het bericht staat er al; dat is niet terug te draaien."""

        class _Stuk(_Sessie):
            async def commit(self):
                raise RuntimeError("database weg")

        svc = _svc(sessie=_Stuk())
        # Mag geen exception opleveren.
        await svc._onthoud_post(uuid4(), "kanaal1", "post123")


class TestPostAlertLegtVast:
    """De bedrading, niet alleen de bouwsteen.

    De eerste versie van deze tests riep `_onthoud_post` rechtstreeks aan.
    Daardoor bleven ze groen toen de aanroep uit `post_alert` werd
    gesloopt: precies de schakel die de PR beloofde te herstellen. Deze
    tests draaien `post_alert` zelf.
    """

    def _svc_met_kanaal(self, mm: _Mattermost, sessie: _Sessie, abo):
        svc = _svc(mattermost=mm, sessie=sessie)

        async def _lijst(_item_id):
            return [abo]

        svc.abonnement_repo = SimpleNamespace(list_abonnementen_voor_item=_lijst)

        async def _execute(_stmt):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(
                    all=lambda: [SimpleNamespace(channel_id="kanaal-1")]
                )
            )

        sessie.execute = _execute
        return svc

    async def test_post_alert_onthoudt_het_bericht(self):
        """Zonder deze rij kan een wegklik nergens aan worden toegewezen."""
        mm = _Mattermost(post_id="post-abc")
        sessie = _Sessie()
        abo = _abonnement(minimum_relevantie=20)
        svc = self._svc_met_kanaal(mm, sessie, abo)

        gepost = await svc.post_alert(_item(relevantie_score=85, categorie="bijlage"))

        assert gepost == 1
        assert [r.post_id for r in sessie.toegevoegd] == ["post-abc"]

    async def test_onder_de_drempel_geen_bericht_en_geen_rij(self):
        """Score 12 bij drempel 20: het gemeten geval van 28 september."""
        mm = _Mattermost(post_id="post-abc")
        sessie = _Sessie()
        abo = _abonnement(minimum_relevantie=20)
        svc = self._svc_met_kanaal(mm, sessie, abo)

        gepost = await svc.post_alert(_item(relevantie_score=12, categorie="bijlage"))

        assert gepost == 0
        assert mm.berichten == []
        assert sessie.toegevoegd == []

    async def test_mislukte_post_levert_geen_rij_op(self):
        """Een rij zonder post zou naar een bericht wijzen dat er niet is."""
        mm = _Mattermost(post_id=None)
        sessie = _Sessie()
        abo = _abonnement(minimum_relevantie=20)
        svc = self._svc_met_kanaal(mm, sessie, abo)

        gepost = await svc.post_alert(_item(relevantie_score=85, categorie="bijlage"))

        assert gepost == 0
        assert sessie.toegevoegd == []


class TestPostIdUitDeRespons:
    """`send_channel_message` geeft het post-id terug, niet `True`.

    Dat was de ontbrekende schakel: met een bool is een reactie nergens
    aan toe te wijzen. Een mutatie die `return True` terugzet moet hier
    omvallen.
    """

    async def _post(self, antwoord: dict, status: int = 200) -> str | None:
        from bouwmeester.services.mattermost_service import MattermostService

        class _Resp:
            status_code = status

            def raise_for_status(self):
                pass

            def json(self):
                return antwoord

        class _Client:
            async def post(self, _url, json=None):
                return _Resp()

        svc = MattermostService.__new__(MattermostService)

        async def _get_client():
            return _Client()

        svc._get_client = _get_client
        return await svc.send_channel_message("kanaal-1", "tekst", None)

    async def test_geeft_het_id_uit_de_respons(self):
        assert await self._post({"id": "post-xyz"}) == "post-xyz"

    async def test_respons_zonder_id_telt_als_mislukt(self):
        assert await self._post({}) is None

    async def test_leeg_id_telt_als_mislukt(self):
        """Anders zou een lege string als post-id worden opgeslagen."""
        assert await self._post({"id": ""}) is None


class TestWebsocketTeltDeWegklik:
    """De laatste schakel: een "x" op een alert moet meetellen."""

    def _svc(self, rij, geteld: list):
        from bouwmeester.services.mattermost_websocket_service import (
            MattermostWebsocketService,
        )

        svc = MattermostWebsocketService.__new__(MattermostWebsocketService)
        svc._bot_user_id = "bot1"
        return svc

    async def test_x_op_een_alert_telt(self, monkeypatch):
        geteld: list = []
        item_id = uuid4()

        await _draai_reactie(monkeypatch, geteld, rij=(item_id,), emoji="x")

        assert geteld == [item_id]

    async def test_onbekende_post_telt_niet(self, monkeypatch):
        """Dan is het geen kamerstuk en mag het lead-pad het proberen."""
        geteld: list = []

        afgehandeld = await _draai_reactie(monkeypatch, geteld, rij=None, emoji="x")

        assert geteld == []
        assert afgehandeld is False

    async def test_dispatch_roept_de_kamerstuk_lookup_aan(self, monkeypatch):
        """Via `_dispatch_reaction_added`, niet via de losse methode.

        De eerste versie testte alleen `_verwerk_kamerstuk_reactie` zelf.
        Daardoor bleef alles groen toen de aanroep uit `_dispatch_reaction_added`
        werd gesloopt: de methode werkte, maar niets riep hem nog aan.
        """
        from bouwmeester.services import mattermost_websocket_service as mod

        gezien: list = []

        async def _verwerk(self, post_id, emoji_name):
            gezien.append((post_id, emoji_name))
            return True

        monkeypatch.setattr(
            mod.MattermostWebsocketService, "_verwerk_kamerstuk_reactie", _verwerk
        )

        svc = mod.MattermostWebsocketService.__new__(mod.MattermostWebsocketService)
        svc._bot_user_id = "bot1"
        monkeypatch.setattr(
            mod.MattermostWebsocketService,
            "_parse_reaction",
            lambda self, msg: {
                "user_id": "mens1",
                "post_id": "post-abc",
                "emoji_name": "x",
            },
        )

        await svc._dispatch_reaction_added({})

        assert gezien == [("post-abc", "x")]

    async def test_de_bot_klikt_zichzelf_niet_weg(self, monkeypatch):
        """De guard op `_bot_user_id` draagt sinds deze PR het hele mechanisme.

        De bot plaatst de "x" zelf, als knop. Valt deze guard weg, dan
        markeert elk alert zichzelf als niet-relevant op het moment van
        posten: stil, met de teller oplopend en zonder dat er iemand
        geklikt heeft. Daarom staat hij hier vast, en niet alleen in de
        code.
        """
        from bouwmeester.services import mattermost_websocket_service as mod

        gezien: list = []

        async def _verwerk(self, post_id, emoji_name):
            gezien.append((post_id, emoji_name))
            return True

        monkeypatch.setattr(
            mod.MattermostWebsocketService, "_verwerk_kamerstuk_reactie", _verwerk
        )
        monkeypatch.setattr(
            mod.MattermostWebsocketService,
            "_parse_reaction",
            lambda self, msg: {
                "user_id": "bot1",
                "post_id": "post-abc",
                "emoji_name": "x",
            },
        )

        svc = mod.MattermostWebsocketService.__new__(mod.MattermostWebsocketService)
        svc._bot_user_id = "bot1"

        await svc._dispatch_reaction_added({})

        assert gezien == []

    async def test_een_kapotte_lookup_blokkeert_het_lead_pad_niet(self, monkeypatch):
        """Weten we het niet, dan mag het suggested-lead-pad het proberen.

        "x" zit in beide tabellen. Een databasefout tijdens het zoeken zegt
        niets over waar deze post bij hoort, dus `True` teruggeven zou een
        wegklik op een lead opslokken die daarna nergens terechtkomt.
        """
        geteld: list = []

        afgehandeld = await _draai_reactie(
            monkeypatch, geteld, rij=None, emoji="x", lookup_faalt=True
        )

        assert geteld == []
        assert afgehandeld is False

    async def test_een_kapotte_telling_gaat_niet_alsnog_naar_het_lead_pad(
        self, monkeypatch
    ):
        """Hier weten we het wél: de post hoort bij een kamerstuk.

        Het lead-pad zou hem toch niet vinden, dus doorgeven levert alleen
        een tweede vergeefse lookup op. Andersom dan de test hierboven, en
        dat verschil is precies waarom de lookup en het tellen elk hun
        eigen try hebben.
        """
        geteld: list = []

        afgehandeld = await _draai_reactie(
            monkeypatch, geteld, rij=(uuid4(),), emoji="x", tellen_faalt=True
        )

        assert geteld == []
        assert afgehandeld is True

    async def test_andere_emoji_telt_niet(self):
        """Alleen "x" is wegklikken; "eyes" heeft nog geen actie."""
        from bouwmeester.services.mattermost_websocket_service import (
            MattermostWebsocketService,
        )

        svc = MattermostWebsocketService.__new__(MattermostWebsocketService)
        assert await svc._verwerk_kamerstuk_reactie("post-abc", "eyes") is False


async def _draai_reactie(
    monkeypatch,
    geteld: list,
    rij,
    emoji: str,
    lookup_faalt: bool = False,
    tellen_faalt: bool = False,
) -> bool:
    """Draai `_verwerk_kamerstuk_reactie` met een vervangen sessie."""
    from contextlib import asynccontextmanager

    from bouwmeester.services import mattermost_websocket_service as mod
    from bouwmeester.services import parlementair_alert_service as alert_mod

    class _Sess:
        async def execute(self, _stmt):
            if lookup_faalt:
                raise RuntimeError("database weg")
            return SimpleNamespace(first=lambda: rij)

        async def commit(self):
            pass

        async def rollback(self):
            pass

    @asynccontextmanager
    async def _sessie():
        yield _Sess()

    monkeypatch.setattr(mod, "async_session", _sessie)

    class _Alert:
        def __init__(self, _session):
            pass

        async def markeer_niet_relevant(self, item_id):
            if tellen_faalt:
                raise RuntimeError("tellen ging mis")
            geteld.append(item_id)

    monkeypatch.setattr(alert_mod, "ParlementairAlertService", _Alert)

    svc = mod.MattermostWebsocketService.__new__(mod.MattermostWebsocketService)
    return await svc._verwerk_kamerstuk_reactie("post-abc", emoji)
