"""Notifications and generated work reach only who may read what they name.

A notification names an item; a Mattermost post lands in a channel others
read; a task the system generates is placed somewhere.  Each asks the
decision point what the item's own route asks.  Uses ``world`` from
``tests/authz_world.py``.
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import can
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.notification import Notification
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.signaalcontext import Signaalcontext
from bouwmeester.models.task import Task
from bouwmeester.repositories.parlementair_abonnement import (
    ParlementairAbonnementRepository,
)
from bouwmeester.services.llm.base import KamerstukAlertResult
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.opdracht_task_service import OpdrachtTaskService
from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)
from tests.authz_world import (
    World,
    add,
    make_item,
    notifications,
    opdracht,
    perm_ctx,
    request,
    rp,
)
from tests.factories import make_org, make_person, place


async def _stakeholders(w: World, node: str, *holders: str) -> None:
    """betrokken on a node for people, or for an eenheid as ``@<key>``."""
    await add(w, *(
        rp("corpus_node", w.res[node], "betrokken", eenheid=w.org[h[1:]])
        if h.startswith("@")
        else rp("corpus_node", w.res[node], "betrokken", person=w.person[h])
        for h in holders
    ))  # fmt: skip


async def _outsider(w: World):
    """Someone placed far away: sees none of the world's items."""
    far = await make_org(w.db, "Ver weg", "ministerie")
    person = await make_person(w.db, "Buitenstaander")
    await place(w.db, person, far)
    w.person["outsider"] = person
    return person


async def _node(w: World, key: str) -> CorpusNode:
    return await w.db.get(CorpusNode, w.res[key])


# Each builder adds stakeholders and sends; returns what was sent.


async def _task_completed(w):
    """role_only reads the directie node (a role) but not the team's task."""
    await _stakeholders(w, "node_directie", "role_only", "super_admin", "@team")
    task = await w.db.get(Task, w.res["task_team"])
    return await NotificationService(w.db).notify_task_completed(task)


async def _opdracht_on_directie_node(w) -> Opdracht:
    row = await w.db.get(Opdracht, w.res["opdracht_directie"])
    row.instrument_id = w.res["node_directie"]
    await _stakeholders(w, "node_directie", "role_only", "super_admin")
    return row


async def _opdracht_assigned(w):
    row = await _opdracht_on_directie_node(w)
    row.verantwoordelijke_id = (await _outsider(w)).id
    await w.db.flush()
    return await NotificationService(w.db).notify_opdracht_assigned(row)


async def _opdracht_status(w):
    row = await _opdracht_on_directie_node(w)
    svc = NotificationService(w.db)
    return await svc.notify_opdracht_status_changed(row, "concept")


async def _import_with_eenheid_grant(w):
    """A grant to an eenheid has no person; it used to break the import."""
    await _stakeholders(w, "node_team", "viewer", "@team")
    return await NotificationService(w.db).notify_parlementair_item_imported(
        await _node(w, "node_free"), [await _node(w, "node_team")]
    )


async def _import_of_unreadable_item(w):
    await _stakeholders(w, "node_directie", "role_only")
    return await NotificationService(w.db).notify_parlementair_item_imported(
        await _node(w, "node_elders"), [await _node(w, "node_directie")]
    )


async def _node_updated(w):
    await _stakeholders(w, "node_team", "viewer", "@team")
    node = await _node(w, "node_team")
    svc = NotificationService(w.db)
    return await svc.notify_node_updated(node, w.person["super_admin"])


# (builder, who receives it)
SENDS = [
    (_task_completed, {"super_admin"}),
    (_opdracht_assigned, {"super_admin"}),
    (_opdracht_status, {"super_admin"}),
    (_import_with_eenheid_grant, {"viewer"}),
    (_import_of_unreadable_item, set()),
    (_node_updated, {"viewer"}),
]


@pytest.mark.parametrize(
    ("send", "receivers"), SENDS, ids=[s.__name__ for s, _ in SENDS]
)
async def test_notification_goes_only_to_readers(world, send, receivers):
    sent = await send(world)
    want = sorted(world.person[who].id for who in receivers)
    assert sorted(n.person_id for n in sent) == want


async def test_edge_notification_hides_an_unreadable_end(world):
    team_node = await _node(world, "node_team")
    elders_node = await _node(world, "node_elders")
    viewer, admin = world.person["viewer"], world.person["super_admin"]
    # the viewer does not see the elders node, super_admin sees both
    await _stakeholders(world, "node_team", "viewer", "@team")
    await _stakeholders(world, "node_elders", "super_admin")
    sent = await NotificationService(world.db).notify_edge_created(
        team_node, elders_node
    )
    by_person = {n.person_id: n for n in sent}
    assert set(by_person) == {viewer.id, admin.id}
    hidden = by_person[viewer.id]
    assert elders_node.title not in hidden.title + hidden.message
    assert hidden.related_node_id == team_node.id
    assert team_node.title in by_person[admin.id].message
    assert elders_node.title in by_person[admin.id].message


async def test_assigning_a_lead_notifies_only_an_assignee_who_can_read_it(world):
    outsider = await _outsider(world)
    reader = world.person["role_only"]  # contributor on the lead's initiatief
    for person in (outsider, reader):
        body = {"assignee_id": str(person.id)}
        resp = await request(world, "super_admin", "PUT", "/api/leads/{lead}", body)
        assert resp.is_success, resp.text
    lead_notes = Notification.related_lead_id == world.res["lead"]

    async def got(person) -> int:
        stmt = select(Notification).where(
            Notification.person_id == person.id, lead_notes
        )
        return len((await world.db.scalars(stmt)).all())

    assert await got(outsider) == 0
    assert await got(reader) == 1


async def test_mention_needs_read_access_and_carries_the_caller(world):
    svc = NotificationService(world.db)
    viewer = world.person["viewer"]
    hidden = await svc.notify_mention(
        viewer.id, "node", "Dossier elders", source_node_id=world.res["node_elders"]
    )
    shown = await svc.notify_mention(
        viewer.id, "node", "Teamdossier", source_node_id=world.res["node_team"]
    )
    # A mention without an item (an eenheid description, a message) is sent.
    plain = await svc.notify_mention(viewer.id, "organisatie", "Team")
    assert hidden is None
    assert shown is not None and shown.person_id == viewer.id
    assert plain is not None

    mentioned = world.person["afd_editor"]
    body = {
        "title": f"Taak {uuid.uuid4().hex[:6]}",
        "description": "Zie [@Redacteur](user:{p_afd_editor})",
        "node_id": "{node_team}",
        "organisatie_eenheid_id": "{eenheid_team}",
        "assignee_id": "{p_viewer}",
    }
    resp = await request(world, "team_editor", "POST", "/api/tasks", body)
    assert resp.status_code == 201, resp.text
    [note] = await notifications(world, mentioned.id, "mention")
    assert note.sender_id == world.person["team_editor"].id


async def test_parlementair_notification_is_a_dm_not_a_channel_post(world):
    notification = Notification(
        id=uuid.uuid4(),
        person_id=world.person["viewer"].id,
        type="politieke_input_imported",
        title="Nieuw(e) motie: X",
        message="Motie 'X' is mogelijk relevant voor 'Teamdossier'.",
    )
    service = MattermostService(world.db)
    with (
        patch.object(service, "is_enabled", AsyncMock(return_value=True)),
        patch.object(service, "send_dm", AsyncMock(return_value=True)) as send_dm,
        patch.object(service, "send_channel_message", AsyncMock()) as to_channel,
        patch.object(service, "_cfg", return_value="kanaal"),
    ):
        assert await service.send_notification(notification)
    to_channel.assert_not_awaited()
    assert send_dm.await_args.args[0] == world.person["viewer"].id


# ---------------------------------------------------------------------------
# Parliamentary alerts: each scope sees only its own context and terms
# ---------------------------------------------------------------------------


class _FakeLLM:
    """Echoes the scope's context back, so a leak shows up in the message."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def summarize_kamerstuk_alert(self, **kwargs):
        self.calls.append(kwargs)
        ctx = kwargs["signaalcontext"]
        return KamerstukAlertResult(
            samenvatting=f"Samenvatting: {ctx}",
            relevantie_score=80,
            reden=f"Reden: {ctx}",
            actie=f"Actie: {ctx}",
        )


async def test_parlementair_alert_keeps_each_scope_to_itself(world, monkeypatch):
    """One item found by two initiatieven, each with its own term, context
    and channel."""
    other = Initiatief(id=uuid.uuid4(), naam=f"Ander {uuid.uuid4().hex[:6]}")
    world.db.add(other)
    item = await make_item(world)
    item.llm_samenvatting = "Algemene samenvatting."
    item.extra_data = {"categorie": "overig"}
    abonnementen = []
    for n, scope_id in enumerate((world.res["initiatief"], other.id)):
        abonnement = ParlementairAbonnement(
            scope_type="initiatief", scope_id=scope_id, term=f"term-{n}",
            term_genormaliseerd=f"term-{n}", minimum_relevantie=0,
        )  # fmt: skip
        world.db.add_all([
            abonnement,
            Signaalcontext(
                scope_type="initiatief", scope_id=scope_id, tekst=f"geheim-{n}"
            ),
            MattermostChannelLink(
                channel_id=f"{n}" * 26, channel_name=f"kanaal-{n}",
                channel_display_name=f"Kanaal {n}", scope_type="initiatief",
                scope_id=scope_id, parlementaire_alerts_enabled=True,
            ),
        ])  # fmt: skip
        abonnementen.append(abonnement)
    await world.db.flush()
    await ParlementairAbonnementRepository(world.db).registreer_treffers(
        item.id, [a.id for a in abonnementen]
    )
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

    assert await ParlementairImportService(world.db)._alert_kamerstuk(item.id) == 2
    # One prompt per scope, with only that scope's term and context.
    assert sorted((c["zoektermen"], c["signaalcontext"]) for c in llm.calls) == [
        (["term-0"], "geheim-0"),
        (["term-1"], "geheim-1"),
    ]
    for own, other_n in ((0, 1), (1, 0)):
        message = sent[f"{own}" * 26]
        assert f"geheim-{own}" in message and f"term-{own}" in message
        assert f"geheim-{other_n}" not in message
        assert f"term-{other_n}" not in message
    # Nothing of either scope is stored on the shared item.
    await world.db.refresh(item)
    assert item.llm_samenvatting == "Algemene samenvatting."
    stored = json.dumps(item.extra_data)
    assert "geheim" not in stored and "relevantie" not in stored


# ---------------------------------------------------------------------------
# Opdracht worker tasks live where the opdracht lives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gever", "nemer", "lands_in", "title"),
    [
        ("elders", None, "elders", "Opdracht formaliseren: Geheime opdracht"),
        (None, "elders", "elders", None),  # falls back to the opdrachtnemer
        (None, None, None, "Opdracht formaliseren"),  # no eenheid: generic title
    ],
)
async def test_opdracht_task_lives_in_the_opdracht_eenheid(
    world, gever, nemer, lands_in, title
):
    """The instrument's readers and editors do not get the opdracht's task."""
    row = opdracht(
        world,
        "Geheime opdracht",
        gever,
        instrument_id=world.res["node_team"],
        verantwoordelijke_id=world.person["viewer"].id,
        opdrachtnemer_eenheid_id=world.org[nemer].id if nemer else None,
    )
    await add(world, row)
    await OpdrachtTaskService(world.db).on_opdracht_created(row)
    (task,) = (
        await world.db.scalars(select(Task).where(Task.opdracht_id == row.id))
    ).all()
    assert task.organisatie_eenheid_id == (world.org[lands_in].id if lands_in else None)
    if title:
        assert task.title == title
    if lands_in:
        ctx = await perm_ctx(world, "team_editor")
        assert not await can(world.db, ctx, "task:read", "task", task.id)
        assert not await can(world.db, ctx, "task:update", "task", task.id)
