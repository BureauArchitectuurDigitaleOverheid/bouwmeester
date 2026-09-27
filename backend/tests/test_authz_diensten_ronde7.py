"""Background services keep what they produce where it belongs (round 7).

Uses ``world`` from ``tests/authz_world.py``.
"""

import json
import uuid

from sqlalchemy import select

from bouwmeester.core.authz import can
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.models.signaalcontext import Signaalcontext
from bouwmeester.models.task import Task
from bouwmeester.repositories.parlementair_abonnement import (
    ParlementairAbonnementRepository,
)
from bouwmeester.services.llm.base import KamerstukAlertResult
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.opdracht_task_service import OpdrachtTaskService
from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)
from tests.authz_world import World, add_directie_admin, make_item, perm_ctx
from tests.factories import client_as

# ---------------------------------------------------------------------------
# Opdracht worker tasks live where the opdracht lives
# ---------------------------------------------------------------------------


async def _opdracht_tasks(w: World, **placing) -> list[Task]:
    opdracht = Opdracht(
        type="opdracht",
        titel="Geheime opdracht",
        begrotingsjaar=2026,
        instrument_id=w.res["node_team"],
        verantwoordelijke_id=w.person["viewer"].id,
        **placing,
    )
    w.db.add(opdracht)
    await w.db.flush()
    await OpdrachtTaskService(w.db).on_opdracht_created(opdracht)
    return list(
        (await w.db.scalars(select(Task).where(Task.opdracht_id == opdracht.id))).all()
    )


async def test_opdracht_task_lives_in_the_opdracht_eenheid(world):
    """The instrument's readers and editors do not get the opdracht's task."""
    (task,) = await _opdracht_tasks(world, opdrachtgever_id=world.org["elders"].id)

    assert task.organisatie_eenheid_id == world.org["elders"].id
    assert task.title == "Opdracht formaliseren: Geheime opdracht"
    ctx = await perm_ctx(world, "team_editor")
    assert not await can(world.db, ctx, "task:read", "task", task.id)
    assert not await can(world.db, ctx, "task:update", "task", task.id)


async def test_opdracht_task_falls_back_to_the_opdrachtnemer(world):
    (task,) = await _opdracht_tasks(
        world, opdrachtnemer_eenheid_id=world.org["elders"].id
    )

    assert task.organisatie_eenheid_id == world.org["elders"].id


async def test_opdracht_task_without_eenheid_has_a_generic_title(world):
    (task,) = await _opdracht_tasks(world)

    assert task.organisatie_eenheid_id is None
    assert task.title == "Opdracht formaliseren"


# ---------------------------------------------------------------------------
# Parliamentary alerts: each scope sees only its own context and terms
# ---------------------------------------------------------------------------


class _FakeLLM:
    """Echoes the scope's context back, so a leak shows up in the message."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def summarize_kamerstuk_alert(self, **kwargs):
        self.calls.append(kwargs)
        return KamerstukAlertResult(
            samenvatting=f"Samenvatting: {kwargs['signaalcontext']}",
            relevantie_score=80,
            reden=f"Reden: {kwargs['signaalcontext']}",
            actie=f"Actie: {kwargs['signaalcontext']}",
        )


async def _two_scopes(w: World) -> tuple[ParlementairItem, list[str]]:
    """One item found by two initiatieven, each with its own term, context
    and channel."""
    other = Initiatief(id=uuid.uuid4(), naam=f"Ander {uuid.uuid4().hex[:6]}")
    w.db.add(other)
    item = await make_item(w)
    item.llm_samenvatting = "Algemene samenvatting."
    item.extra_data = {"categorie": "overig"}
    abonnementen = []
    for n, scope_id in enumerate((w.res["initiatief"], other.id)):
        abonnement = ParlementairAbonnement(
            scope_type="initiatief",
            scope_id=scope_id,
            term=f"term-{n}",
            term_genormaliseerd=f"term-{n}",
            minimum_relevantie=0,
        )
        w.db.add_all(
            [
                abonnement,
                Signaalcontext(
                    scope_type="initiatief", scope_id=scope_id, tekst=f"geheim-{n}"
                ),
                MattermostChannelLink(
                    channel_id=f"{n}" * 26,
                    channel_name=f"kanaal-{n}",
                    channel_display_name=f"Kanaal {n}",
                    scope_type="initiatief",
                    scope_id=scope_id,
                    parlementaire_alerts_enabled=True,
                ),
            ]
        )
        abonnementen.append(abonnement)
    await w.db.flush()
    await ParlementairAbonnementRepository(w.db).registreer_treffers(
        item.id, [a.id for a in abonnementen]
    )
    return item, [f"{n}" * 26 for n in range(2)]


async def test_parlementair_alert_keeps_each_scope_to_itself(world, monkeypatch):
    item, channels = await _two_scopes(world)
    llm = _FakeLLM()
    sent: dict[str, str] = {}

    async def _llm_for(_sensitivity, _db):
        return llm

    async def _enabled(_self):
        return True

    async def _send(_self, channel_id, text, props):
        sent[channel_id] = json.dumps(props)
        return True

    monkeypatch.setattr(
        "bouwmeester.services.parlementair_import_service.get_llm_service_for",
        _llm_for,
    )
    monkeypatch.setattr(MattermostService, "is_enabled", _enabled)
    monkeypatch.setattr(MattermostService, "send_channel_message", _send)

    gepost = await ParlementairImportService(world.db)._alert_kamerstuk(item.id)

    assert gepost == 2
    # One prompt per scope, with only that scope's term and context.
    assert sorted((c["zoektermen"], c["signaalcontext"]) for c in llm.calls) == [
        (["term-0"], "geheim-0"),
        (["term-1"], "geheim-1"),
    ]
    for own, other in ((0, 1), (1, 0)):
        message = sent[channels[own]]
        assert f"geheim-{own}" in message and f"term-{own}" in message
        assert f"geheim-{other}" not in message
        assert f"term-{other}" not in message
    # Nothing of either scope is stored on the shared item.
    await world.db.refresh(item)
    assert item.llm_samenvatting == "Algemene samenvatting."
    stored = json.dumps(item.extra_data)
    assert "geheim" not in stored and "relevantie" not in stored


# ---------------------------------------------------------------------------
# Completing a review closes the review task, not every linked task
# ---------------------------------------------------------------------------


async def test_complete_review_leaves_other_units_tasks_open(world):
    """Anyone may link a task to an item; the reviewer closes only their own."""
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    item = await make_item(world, "node_directie")
    review = await ParlementairImportService(world.db).create_review_task(
        item, affected_nodes=[]
    )
    elders = await world.db.get(Task, world.res["task_elders"])
    elders.parlementair_item_id = item.id
    await world.db.flush()

    async with client_as(world.db, world.person["ministry_admin"]) as c:
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json={"eigenaar_id": str(world.person["manager"].id), "tasks": []},
        )

    assert resp.status_code == 200, resp.text
    await world.db.refresh(review)
    await world.db.refresh(elders)
    assert review.status == "done"
    assert elders.status == "open"


async def test_item_response_drops_a_stored_scope_judgement(world):
    """Items from before the fix carry one scope's judgement in extra_data."""
    item = await make_item(world, "node_team")
    item.extra_data = {
        "categorie": "overig",
        "relevantie_reden": "geheim",
        "actie": "x",
    }
    await world.db.flush()

    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.get(f"/api/parlementair/imports/{item.id}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["extra_data"] == {"categorie": "overig"}
