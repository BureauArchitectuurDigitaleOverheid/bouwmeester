"""Services and their routes ask what REST asks (round-2 review fixes).

Uses ``world`` from ``tests/authz_world.py``.
"""

import uuid

import pytest

from bouwmeester.models.task import Task
from bouwmeester.services.chat_service import _authorize_write_tool
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
