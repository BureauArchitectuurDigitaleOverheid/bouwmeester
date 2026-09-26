"""Services and their routes ask what REST asks (round-2 review fixes).

Uses ``world`` from ``tests/authz_world.py``.
"""

import uuid

import pytest

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.task import Task
from bouwmeester.services.caller import caller_for
from bouwmeester.services.chat_service import _authorize_write_tool
from bouwmeester.services.mattermost_slash_service import MattermostSlashService
from bouwmeester.services.notification_service import NotificationService
from tests.authz_world import World
from tests.factories import client_as

# ---------------------------------------------------------------------------
# Chat create_task: the rules of POST /tasks
# ---------------------------------------------------------------------------


async def _directie_task(w: World) -> uuid.UUID:
    """A task of the directie: visible to the team below, not writable there."""
    task = Task(
        title="Directietaak",
        node_id=w.res["node_directie"],
        organisatie_eenheid_id=w.org["directie"].id,
        status="open",
    )
    w.db.add(task)
    await w.db.flush()
    return task.id


_TEAM = "{eenheid_team}"

# (who, chat args with ``{key}`` from the world, expected refusal?)
CREATE_TASK_CASES = [
    # an invisible node, placed in an eenheid the caller may create in
    (
        "team_editor",
        {"node_id": "{node_elders}", "organisatie_eenheid_id": _TEAM},
        True,
    ),
    # a parent task that is visible but not writable
    ("team_editor", {"node_id": "{node_team}", "parent_task_id": "{dir_task}"}, True),
    # a parent task the caller may change
    ("team_editor", {"node_id": "{node_team}", "parent_task_id": "{task_team}"}, False),
    ("team_editor", {"node_id": "{node_team}", "organisatie_eenheid_id": _TEAM}, False),
    ("viewer", {"node_id": "{node_team}"}, True),
]


def _rest_body(args: dict) -> dict:
    body = {"title": "x", "node_id": args["node_id"]}
    if "parent_task_id" in args:
        body["parent_id"] = args["parent_task_id"]
    if "organisatie_eenheid_id" in args:
        body["organisatie_eenheid_id"] = args["organisatie_eenheid_id"]
    return body


@pytest.mark.parametrize(
    ("who", "args", "refused"),
    CREATE_TASK_CASES,
    ids=[
        f"{c[0]}-{'-'.join(v[1:-1] for v in c[1].values())}" for c in CREATE_TASK_CASES
    ],
)
async def test_chat_create_task_asks_what_post_tasks_asks(world, who, args, refused):
    values = {k: str(v) for k, v in world.res.items()}
    values["dir_task"] = str(await _directie_task(world))
    filled = {k: v.format(**values) for k, v in args.items()} | {"title": "x"}
    person = world.person[who]

    refusal = await _authorize_write_tool("create_task", filled, world.db, person.id)
    async with client_as(world.db, person) as c:
        resp = await c.post("/api/tasks", json=_rest_body(filled))

    assert (refusal is not None) is refused, refusal
    assert (resp.status_code in (403, 404)) is refused, resp.text


# ---------------------------------------------------------------------------
# Chat and slash commands resolve their caller the same way
# ---------------------------------------------------------------------------


async def test_chat_and_slash_share_one_caller(world):
    person = world.person["team_editor"]
    chat = await caller_for(world.db, person.id)
    slash = await MattermostSlashService(world.db)._caller(person.id)

    assert slash is not None
    assert slash.perm_ctx is chat.perm_ctx  # one context per session
    assert slash.org_ctx is chat.org_ctx
    # a command always comes from a known person, never anonymous
    assert await MattermostSlashService(world.db)._caller(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# Edge notifications name the other node only to those who can read it
# ---------------------------------------------------------------------------


async def test_edge_notification_hides_an_unreadable_end(world):
    db = world.db
    team_node = await db.get(CorpusNode, world.res["node_team"])
    elders_node = await db.get(CorpusNode, world.res["node_elders"])
    viewer = world.person["viewer"]  # sees the team node, not the elders one
    super_admin = world.person["super_admin"]  # sees both
    db.add_all(
        [
            ResourcePermission(
                person_id=viewer.id,
                resource_type="corpus_node",
                resource_id=team_node.id,
                rol="betrokken",
            ),
            ResourcePermission(
                person_id=super_admin.id,
                resource_type="corpus_node",
                resource_id=elders_node.id,
                rol="betrokken",
            ),
            # a grant to an eenheid has no person to notify
            ResourcePermission(
                organisatie_eenheid_id=world.org["team"].id,
                resource_type="corpus_node",
                resource_id=team_node.id,
                rol="betrokken",
            ),
        ]
    )
    await db.flush()

    sent = await NotificationService(db).notify_edge_created(team_node, elders_node)

    by_person = {n.person_id: n for n in sent}
    assert set(by_person) == {viewer.id, super_admin.id}
    hidden = by_person[viewer.id]
    assert elders_node.title not in hidden.title + hidden.message
    assert hidden.related_node_id == team_node.id
    full = by_person[super_admin.id]
    assert team_node.title in full.message
    assert elders_node.title in full.message
