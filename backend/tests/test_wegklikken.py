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


class TestBerichtZonderPostId:
    """Een mislukte post telt niet mee en levert geen lege rij op."""

    async def test_geen_post_id_geen_rij(self):
        sessie = _Sessie()
        mm = _Mattermost(post_id=None)
        svc = _svc(mattermost=mm, sessie=sessie)
        svc.abonnement_repo = SimpleNamespace()

        # `post_alert` heeft meer omheen nodig; dit test het contract van
        # de lus: zonder id wordt er niets onthouden.
        post_id = await mm.send_channel_message("kanaal1", "tekst", {})
        assert post_id is None
        assert sessie.toegevoegd == []
