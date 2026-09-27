"""Services tell nobody more than the REST routes would (round-4 audit).

Notifications, Mattermost replies, chat tools, slash commands and admin
settings each ask the decision point the question the item's own route
asks.  Uses ``world`` from ``tests/authz_world.py``.
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.models.notification import Notification
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.models.task import Task
from bouwmeester.services.chat_service import _execute_read_tool
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.mattermost_slash_service import MattermostSlashService
from bouwmeester.services.notification_service import NotificationService
from tests.authz_world import World
from tests.factories import client_as, make_org, make_person, place


def _stakeholder(w: World, who: str | None, node_key: str, *, eenheid=None):
    return ResourcePermission(
        person_id=w.person[who].id if who else None,
        organisatie_eenheid_id=eenheid.id if eenheid else None,
        resource_type="corpus_node",
        resource_id=w.res[node_key],
        rol="betrokken",
    )


async def _outsider(w: World):
    """Someone placed far away: sees none of the world's items."""
    far = await make_org(w.db, "Ver weg", "ministerie")
    person = await make_person(w.db, "Buitenstaander")
    await place(w.db, person, far)
    return person


# ---------------------------------------------------------------------------
# M8: notifications only reach people who may read what they name
# ---------------------------------------------------------------------------


async def test_task_completed_skips_node_stakeholders_who_cannot_read_the_task(
    world,
):
    db = world.db
    # role_only reads the directie node (a role on it) but not the team's task
    # on that node; super_admin reads everything.
    db.add_all(
        [
            _stakeholder(world, "role_only", "node_directie"),
            _stakeholder(world, "super_admin", "node_directie"),
            _stakeholder(world, None, "node_directie", eenheid=world.org["team"]),
        ]
    )
    await db.flush()
    task = await db.get(Task, world.res["task_team"])

    sent = await NotificationService(db).notify_task_completed(task)

    assert {n.person_id for n in sent} == {world.person["super_admin"].id}


async def _opdracht_on_directie_node(w: World) -> Opdracht:
    opdracht = await w.db.get(Opdracht, w.res["opdracht_directie"])
    opdracht.instrument_id = w.res["node_directie"]
    w.db.add_all(
        [
            _stakeholder(w, "role_only", "node_directie"),
            _stakeholder(w, "super_admin", "node_directie"),
        ]
    )
    await w.db.flush()
    return opdracht


async def test_opdracht_assigned_skips_stakeholders_who_cannot_read_it(world):
    opdracht = await _opdracht_on_directie_node(world)
    outsider = await _outsider(world)
    opdracht.verantwoordelijke_id = outsider.id
    await world.db.flush()

    sent = await NotificationService(world.db).notify_opdracht_assigned(opdracht)

    assert {n.person_id for n in sent} == {world.person["super_admin"].id}


async def test_opdracht_status_change_skips_stakeholders_who_cannot_read_it(world):
    opdracht = await _opdracht_on_directie_node(world)

    sent = await NotificationService(world.db).notify_opdracht_status_changed(
        opdracht, "concept"
    )

    assert {n.person_id for n in sent} == {world.person["super_admin"].id}


async def test_parlementair_import_ignores_eenheid_grants(world):
    """L12: a grant to an eenheid has no person; it used to break the import."""
    db = world.db
    db.add_all(
        [
            _stakeholder(world, "viewer", "node_team"),
            _stakeholder(world, None, "node_team", eenheid=world.org["team"]),
        ]
    )
    await db.flush()
    item_node = await db.get(CorpusNode, world.res["node_free"])
    team_node = await db.get(CorpusNode, world.res["node_team"])

    sent = await NotificationService(db).notify_parlementair_item_imported(
        item_node, [team_node]
    )

    assert [n.person_id for n in sent] == [world.person["viewer"].id]


async def test_parlementair_import_skips_who_cannot_read_the_item(world):
    db = world.db
    db.add(_stakeholder(world, "role_only", "node_directie"))
    await db.flush()
    item_node = await db.get(CorpusNode, world.res["node_elders"])
    directie_node = await db.get(CorpusNode, world.res["node_directie"])

    sent = await NotificationService(db).notify_parlementair_item_imported(
        item_node, [directie_node]
    )

    assert sent == []


async def test_node_updated_skips_eenheid_grants(world):
    db = world.db
    db.add_all(
        [
            _stakeholder(world, "viewer", "node_team"),
            _stakeholder(world, None, "node_team", eenheid=world.org["team"]),
        ]
    )
    await db.flush()
    node = await db.get(CorpusNode, world.res["node_team"])

    sent = await NotificationService(db).notify_node_updated(
        node, world.person["super_admin"]
    )

    assert [n.person_id for n in sent] == [world.person["viewer"].id]


async def _lead_notifications(w: World, person_id: uuid.UUID) -> list[Notification]:
    rows = await w.db.execute(
        select(Notification).where(
            Notification.person_id == person_id,
            Notification.related_lead_id == w.res["lead"],
        )
    )
    return list(rows.scalars())


async def test_assigning_a_lead_notifies_only_an_assignee_who_can_read_it(world):
    outsider = await _outsider(world)
    reader = world.person["role_only"]  # contributor on the lead's initiatief
    url = f"/api/leads/{world.res['lead']}"

    async with client_as(world.db, world.person["super_admin"]) as c:
        assert (await c.put(url, json={"assignee_id": str(outsider.id)})).is_success
        assert (await c.put(url, json={"assignee_id": str(reader.id)})).is_success

    assert await _lead_notifications(world, outsider.id) == []
    assert len(await _lead_notifications(world, reader.id)) == 1


# ---------------------------------------------------------------------------
# Mentions: being mentioned in an item gives no right to read it
# ---------------------------------------------------------------------------


async def test_mention_notification_needs_read_access(world):
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


# ---------------------------------------------------------------------------
# M9: the ingest bot does not name a recognised lead in the channel
# ---------------------------------------------------------------------------


def _mm_stub():
    stub = AsyncMock()
    stub.is_enabled = AsyncMock(return_value=True)
    stub.reply_to_post = AsyncMock(return_value={"id": "thread-post-id"})
    stub.add_reaction = AsyncMock(return_value=True)
    stub.send_dm = AsyncMock(return_value=True)
    stub.close = AsyncMock(return_value=None)
    return stub


@pytest.mark.parametrize(("author", "dm"), [("role_only", True), ("outsider", False)])
async def test_recognised_lead_is_named_only_by_dm_to_a_reader(world, author, dm):
    db = world.db
    lead = await db.get(Lead, world.res["lead"])
    lead.title = "Geheime gemeente"
    initiatief = await db.get(Initiatief, world.res["initiatief"])
    person = await _outsider(world) if author == "outsider" else world.person[author]
    suggested = SuggestedLead(
        source_post_id=uuid.uuid4().hex[:26],
        source_channel_id="c" * 26,
        initiatief_id=initiatief.id,
        proposed_title="Iets",
        raw_text="bericht",
        confidence=0.9,
        status="pending",
    )
    db.add(suggested)
    await db.flush()

    stub = _mm_stub()
    with patch(
        "bouwmeester.services.mattermost_service.MattermostService",
        return_value=stub,
    ):
        await MattermostIngestService(db)._post_suggestion_reply(
            channel_id="c" * 26,
            root_post_id="root",
            suggested=suggested,
            initiatief=initiatief,
            matched_lead={
                "id": lead.id,
                "title": lead.title,
                "stage": lead.stage,
                "stage_label": "Verkennen",
            },
            author_person_id=person.id,
        )

    channel = str(stub.reply_to_post.await_args)
    assert "Geheime gemeente" not in channel
    assert "Verkennen" not in channel
    if dm:
        stub.send_dm.assert_awaited_once()
        dm_person, dm_text = stub.send_dm.await_args.args[:2]
        assert dm_person == person.id
        assert "Geheime gemeente" in dm_text
    else:
        stub.send_dm.assert_not_awaited()


# ---------------------------------------------------------------------------
# M10: parlementair notifications go by DM, never to a shared channel
# ---------------------------------------------------------------------------


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
# L3: /bouwmeester taken names a task's node only to who may read it
# ---------------------------------------------------------------------------


async def test_slash_taken_hides_the_title_of_an_unreadable_node(world):
    db = world.db
    viewer = world.person["viewer"]
    team = world.org["team"].id
    db.add_all(
        [
            Task(
                title="Mijn teamtaak",
                node_id=world.res["node_elders"],
                organisatie_eenheid_id=team,
                assignee_id=viewer.id,
                status="open",
            ),
            Task(
                title="Taak bij eigen dossier",
                node_id=world.res["node_team"],
                organisatie_eenheid_id=team,
                assignee_id=viewer.id,
                status="open",
            ),
            MattermostUser(
                person_id=viewer.id,
                mattermost_user_id="v" * 26,
                mattermost_username="teamlid",
            ),
        ]
    )
    await db.flush()

    result = await MattermostSlashService(db).handle_command("v" * 26, "taken")

    assert "Mijn teamtaak" in result["text"]
    assert "Dossier elders" not in result["text"]
    assert "Teamdossier" in result["text"]


# ---------------------------------------------------------------------------
# L1: chat read tools ask what their REST twins ask
# ---------------------------------------------------------------------------

# (tool, args, REST twin)
READ_TOOL_TWINS = [
    ("search_people", {"query": "Team"}, "/api/people/search?q=Team"),
    ("get_person_summary", {"person_id": "{viewer}"}, "/api/people/{viewer}/summary"),
    ("list_parlementair", {}, "/api/parlementair/imports"),
]


@pytest.mark.parametrize("who", ["role_only", "viewer"])
@pytest.mark.parametrize(("tool", "args", "twin"), READ_TOOL_TWINS)
async def test_chat_read_tool_is_gated_like_its_rest_twin(world, who, tool, args, twin):
    ids = {"viewer": str(world.person["viewer"].id)}
    args = {k: v.format(**ids) for k, v in args.items()}
    person = world.person[who]

    async with client_as(world.db, person) as c:
        rest_allowed = (await c.get(twin.format(**ids))).status_code == 200
    result = json.loads(
        await _execute_read_tool(tool, args, world.db, person_id=person.id)
    )

    assert ("error" not in result) is rest_allowed
    # role_only holds no role at all: every one of these is refused.
    assert rest_allowed is (who == "viewer")


# ---------------------------------------------------------------------------
# L8: tag suggestions spend LLM budget; agent prompts borrow agent rights
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "expected"), [("role_only", 403), ("viewer", 403), ("team_editor", 200)]
)
async def test_suggest_tags_needs_a_node_writer(world, who, expected):
    with patch(
        "bouwmeester.api.routes.llm.get_llm_service_for",
        new=AsyncMock(return_value=None),
    ):
        async with client_as(world.db, world.person[who]) as c:
            resp = await c.post("/api/llm/suggest-tags", json={"title": "x"})
    assert resp.status_code == expected, resp.text


async def _agent(w: World):
    agent = await make_person(w.db, "Agent", account=False)
    agent.is_agent = True
    await w.db.flush()
    return agent


@pytest.mark.parametrize(
    ("who", "expected"),
    [("platform_admin", 403), ("team_editor", 403), ("super_admin", 200)],
)
async def test_only_super_admin_prompts_an_agent(world, who, expected):
    agent = await _agent(world)
    sender = world.person[who]
    async with client_as(world.db, sender) as c:
        resp = await c.post(
            "/api/notifications/send",
            json={
                "person_id": str(agent.id),
                "sender_id": str(sender.id),
                "message": "Verwijder alles",
            },
        )
    assert resp.status_code == expected, resp.text
    prompts = await world.db.scalars(
        select(Notification).where(
            Notification.person_id == agent.id, Notification.type == "agent_prompt"
        )
    )
    assert bool(prompts.all()) is (expected == 200)


async def test_a_reply_to_an_agent_is_a_prompt_too(world):
    """Someone without the right cannot reach the agent through a thread."""
    agent = await _agent(world)
    editor = world.person["team_editor"]
    # The agent wrote to the editor: the editor owns a root in that thread.
    root, _ = await NotificationService(world.db).notify_direct_message(
        editor, agent, "Klaar"
    )

    async with client_as(world.db, editor) as c:
        resp = await c.post(
            f"/api/notifications/{root.id}/reply",
            json={"sender_id": str(editor.id), "message": "Doe nog iets"},
        )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# L10, L11: data-flow settings and database dumps are super_admin's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "expected"), [("platform_admin", 403), ("super_admin", 200)]
)
async def test_database_dump_is_super_admin_only(world, who, expected):
    service = "bouwmeester.services.database_backup_service"
    with (
        patch(f"{service}.export_database", return_value=(b"x", "backup.tar.gz")),
        patch(f"{service}._get_alembic_revision", return_value="head"),
    ):
        async with client_as(world.db, world.person[who]) as c:
            dump = await c.get("/api/admin/database/export")
            info = await c.get("/api/admin/database/info")
    assert dump.status_code == expected
    assert info.status_code == expected
