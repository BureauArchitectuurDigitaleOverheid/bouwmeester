"""De onderste twee schakels van het wegklikken, tegen een echte database.

`test_wegklikken.py` draait bewust zonder database en stubt daarom
`ParlementairAlertService`. Daardoor houdt de dekking op bij
`markeer_niet_relevant` en bleef alles eronder ongemeten: de teller die de
bestaansreden van deze hele PR is kon worden vervangen door `pass` zonder
dat één van 1707 tests omviel. Vier reviewrondes lang is de keten steeds
één schakel hoger vastgelegd terwijl het gat aan de onderkant open bleef.

Deze tests gaan door de echte repository naar echte rijen. Ze hebben
Postgres nodig, net als de rest van de suite die `db_session` gebruikt.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.models.parlementair_treffer import ParlementairTreffer
from bouwmeester.repositories.parlementair_abonnement import (
    ParlementairAbonnementRepository,
)
from bouwmeester.services.parlementair_alert_service import ParlementairAlertService

pytestmark = pytest.mark.asyncio


async def _item(session: AsyncSession, zaak: str) -> ParlementairItem:
    item = ParlementairItem(
        type="motie",
        zaak_id=zaak,
        zaak_nummer=zaak,
        titel="Een stuk waarin de term als gewoon woord valt",
        onderwerp="Onderwerp",
        bron="tweede_kamer",
    )
    session.add(item)
    await session.flush()
    return item


async def _abonnement(
    session: AsyncSession, term: str, scope_id=None
) -> ParlementairAbonnement:
    abo = ParlementairAbonnement(
        scope_type="initiatief",
        scope_id=scope_id or uuid4(),
        term=term,
        term_genormaliseerd=term.lower(),
    )
    session.add(abo)
    await session.flush()
    return abo


async def _treffer(
    session: AsyncSession, item: ParlementairItem, abo: ParlementairAbonnement
) -> None:
    session.add(ParlementairTreffer(parlementair_item_id=item.id, abonnement_id=abo.id))
    await session.flush()


class TestDeHeleKetenVanafDeReactie:
    """Van een binnengekomen "x" tot een vastgelegde ophoging.

    De tests in `test_wegklikken.py` stubben de sessie, dus een ontbrekende
    `commit()` is daar onzichtbaar: `markeer_weggeklikt` doet alleen
    `flush()`, en die verdwijnt bij het afsluiten van de sessie. Hier
    controleert een tweede sessie of de ophoging de eerste heeft overleefd.
    """

    async def test_een_x_op_een_alert_wordt_vastgelegd(
        self, db_session: AsyncSession, monkeypatch
    ):
        from contextlib import asynccontextmanager

        from bouwmeester.models.parlementair_alert_post import ParlementairAlertPost
        from bouwmeester.services import mattermost_websocket_service as ws_mod

        item = await _item(db_session, "2026Z00006")
        abo = await _abonnement(db_session, "Fundament")
        await _treffer(db_session, item, abo)
        db_session.add(
            ParlementairAlertPost(
                parlementair_item_id=item.id,
                channel_id="kanaal-1",
                post_id="post-abc",
            )
        )
        await db_session.commit()

        # De service opent zijn eigen sessie. Die krijgt hier dezelfde
        # verbinding als de test: `db_session` draait in een transactie die
        # na afloop wordt teruggedraaid, dus een tweede verbinding zou de
        # rijen hierboven niet eens zien.
        #
        # Daarom telt deze test ook de commits. `markeer_weggeklikt` doet
        # alleen `flush()`, en met een gedeelde sessie is een ontbrekende
        # `commit()` aan de waarde niet te zien terwijl hij in productie
        # de hele wegklik laat verdampen.
        commits: list = []
        echte_commit = db_session.commit

        async def _commit():
            commits.append(True)
            await echte_commit()

        monkeypatch.setattr(db_session, "commit", _commit)

        @asynccontextmanager
        async def _sessie():
            yield db_session

        monkeypatch.setattr(ws_mod, "async_session", _sessie)

        svc = ws_mod.MattermostWebsocketService.__new__(
            ws_mod.MattermostWebsocketService
        )
        afgehandeld = await svc._verwerk_kamerstuk_reactie("post-abc", "x")

        assert afgehandeld is True
        await db_session.refresh(abo)
        assert abo.weggeklikt_totaal == 1
        assert commits, "zonder commit verdampt de wegklik bij het sluiten"


class TestDrempelViaDeApi:
    """De instelbaarheid is de halve PR en had geen enkele test.

    De PATCH-route kan `minimum_relevantie` stil weggooien: de dropdown
    lijkt dan te werken (het scherm herlaadt), terwijl elke term op 20
    blijft staan. Geen van de abonnementen-endpoints werd getest.
    """

    async def test_patch_slaat_de_drempel_op(self, client, db_session: AsyncSession):
        from bouwmeester.models.initiatief import Initiatief

        init = Initiatief(id=uuid4(), naam="Init")
        db_session.add(init)
        abo = await _abonnement(db_session, "Fundament", scope_id=init.id)
        await db_session.commit()

        resp = await client.patch(
            f"/api/initiatieven/{init.id}/abonnementen/{abo.id}",
            json={"minimum_relevantie": 40},
        )

        assert resp.status_code == 200
        assert resp.json()["minimum_relevantie"] == 40
        await db_session.refresh(abo)
        assert abo.minimum_relevantie == 40

    async def test_patch_zonder_drempel_laat_hem_staan(
        self, client, db_session: AsyncSession
    ):
        """Een PATCH op de notitie mag de drempel niet terugzetten."""
        from bouwmeester.models.initiatief import Initiatief

        init = Initiatief(id=uuid4(), naam="Init")
        db_session.add(init)
        abo = await _abonnement(db_session, "Fundament", scope_id=init.id)
        abo.minimum_relevantie = 40
        await db_session.commit()

        resp = await client.patch(
            f"/api/initiatieven/{init.id}/abonnementen/{abo.id}",
            json={"notitie": "iets anders"},
        )

        assert resp.status_code == 200
        await db_session.refresh(abo)
        assert abo.minimum_relevantie == 40

    async def test_alles_tonen_is_een_geldige_keuze(
        self, client, db_session: AsyncSession
    ):
        """0 is falsy, dus elke `or`-truc in de route zou hem overslaan.

        De route toetst `is not None` en niet de waarheidswaarde. Zonder
        deze test blijft `if payload.minimum_relevantie:` groen, en dan is
        "Alles tonen" de enige keuze die niet opgeslagen wordt.
        """
        from bouwmeester.models.initiatief import Initiatief

        init = Initiatief(id=uuid4(), naam="Init")
        db_session.add(init)
        abo = await _abonnement(db_session, "Fundament", scope_id=init.id)
        abo.minimum_relevantie = 40
        await db_session.commit()

        resp = await client.patch(
            f"/api/initiatieven/{init.id}/abonnementen/{abo.id}",
            json={"minimum_relevantie": 0},
        )

        assert resp.status_code == 200
        await db_session.refresh(abo)
        assert abo.minimum_relevantie == 0


class TestTellerLooptEchtOp:
    """Van `markeer_niet_relevant` tot een opgehoogde kolom in de database."""

    async def test_een_wegklik_hoogt_de_teller_op(self, db_session: AsyncSession):
        item = await _item(db_session, "2026Z00001")
        abo = await _abonnement(db_session, "Fundament")
        await _treffer(db_session, item, abo)

        await ParlementairAlertService(db_session).markeer_niet_relevant(item.id)

        await db_session.refresh(abo)
        assert abo.weggeklikt_totaal == 1

    async def test_elke_term_die_het_stuk_aandroeg_telt_mee(
        self, db_session: AsyncSession
    ):
        """Twee termen, één stuk: beide krijgen de wegklik te zien.

        Dat is het punt van het getal. Het staat op de initiatief-pagina
        naast de term, en moet dus vertellen hoe vaak juist díe term iets
        aandroeg dat de lezer wegklikte.
        """
        item = await _item(db_session, "2026Z00002")
        breed = await _abonnement(db_session, "Fundament")
        smal = await _abonnement(db_session, "NLDD")
        await _treffer(db_session, item, breed)
        await _treffer(db_session, item, smal)

        await ParlementairAlertService(db_session).markeer_niet_relevant(item.id)

        await db_session.refresh(breed)
        await db_session.refresh(smal)
        assert (breed.weggeklikt_totaal, smal.weggeklikt_totaal) == (1, 1)

    async def test_een_term_zonder_treffer_telt_niet_mee(
        self, db_session: AsyncSession
    ):
        """Anders zou elke wegklik elke term van het initiatief raken."""
        item = await _item(db_session, "2026Z00003")
        scope = uuid4()
        met = await _abonnement(db_session, "Fundament", scope_id=scope)
        zonder = await _abonnement(db_session, "NLDD", scope_id=scope)
        await _treffer(db_session, item, met)

        await ParlementairAlertService(db_session).markeer_niet_relevant(item.id)

        await db_session.refresh(met)
        await db_session.refresh(zonder)
        assert (met.weggeklikt_totaal, zonder.weggeklikt_totaal) == (1, 0)

    async def test_de_repository_hoogt_op_vanaf_de_bestaande_stand(
        self, db_session: AsyncSession
    ):
        """Optellen, niet op 1 zetten: een tweede wegklik moet 2 geven."""
        item_een = await _item(db_session, "2026Z00004")
        item_twee = await _item(db_session, "2026Z00005")
        abo = await _abonnement(db_session, "Fundament")
        await _treffer(db_session, item_een, abo)
        await _treffer(db_session, item_twee, abo)

        repo = ParlementairAbonnementRepository(db_session)
        await repo.markeer_weggeklikt(item_een.id)
        await repo.markeer_weggeklikt(item_twee.id)

        await db_session.refresh(abo)
        assert abo.weggeklikt_totaal == 2
