"""The single decision point (``core/authz.py``): resolution and routes.

Uses the shared tree of ``tests/authz_world.py``.  One table covers each
resolution step of ``can()``; a route table checks that the reference
routes (nodes, edges, tasks) and the chat write tools ask the same
question.  Visibility lives in ``test_authz_visibility.py``, the evaluation
endpoint in ``test_authz_evaluations.py``.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from bouwmeester.core.authz import can, require
from bouwmeester.core.org_context import build_org_context
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.shared_access import SharedAccess
from tests.authz_world import (
    assert_can_case,
    assert_route_case,
    can_case_id,
    perm_ctx,
    route_case_id,
)
from tests.factories import client_as

# (who, permission, resource type, resource key or None, eenheid key, expected)
CASES = [
    # 1. super_admin and system roles
    ("super_admin", "node:delete", "corpus_node", "node_directie", None, True),
    ("platform_admin", "org:read", "organisatie_eenheid", "eenheid_elders", None, True),
    ("platform_admin", "node:update", "corpus_node", "node_elders", None, False),
    ("platform_admin", "node:update", "corpus_node", "node_free", None, False),
    # 2. a resource role on the resource itself
    ("role_only", "node:update", "corpus_node", "node_directie", None, True),
    ("role_only", "node:delete", "corpus_node", "node_directie", None, False),
    ("role_only", "node:update", "corpus_node", "node_afdeling", None, False),
    ("role_only", "initiatief:update", "initiatief", "initiatief", None, True),
    # 3. parent delegation
    ("role_only", "lead:update", "lead", "lead", None, True),  # contributor
    ("role_only", "lead:delete", "lead", "lead", None, False),
    ("role_only", "lead_column:update", "lead_column", "lead_column", None, True),
    ("viewer", "lead:update", "lead", "lead", None, False),
    ("team_editor", "edge:update", "edge", "edge_team_directie", None, True),
    ("team_editor", "edge:update", "edge", "edge_directie_elders", None, False),
    ("team_editor", "edge:delete", "edge", "edge_team_directie", None, False),
    ("manager", "edge:delete", "edge", "edge_directie_elders", None, True),
    ("role_only", "edge:update", "edge", "edge_directie_elders", None, True),
    ("afd_editor", "task:update", "task", "task_on_team_node", None, True),
    ("team_editor", "task:update", "task", "task_on_team_node", None, True),
    # a team's task is the team's, not the node owner's
    ("role_only", "task:update", "task", "task_team", None, False),
    # a child permission asked on its parent
    ("team_editor", "edge:create", "corpus_node", "node_team", None, True),
    ("team_editor", "edge:create", "corpus_node", "node_directie", None, False),
    ("role_only", "task:create", "corpus_node", "node_directie", None, True),
    ("role_only", "lead:create", "initiatief", "initiatief", None, True),
    # 4. rights on the eenheid, inherited downward only
    ("afd_editor", "node:update", "corpus_node", "node_afdeling", None, True),
    ("afd_editor", "node:update", "corpus_node", "node_team", None, True),
    ("afd_editor", "node:update", "corpus_node", "node_directie", None, False),
    ("team_editor", "node:update", "corpus_node", "node_directie", None, False),
    ("team_editor", "node:update", "corpus_node", "node_afdeling", None, False),
    ("viewer", "node:update", "corpus_node", "node_team", None, False),
    ("viewer", "node:read", "corpus_node", "node_team", None, True),
    ("manager", "node:delete", "corpus_node", "node_team", None, True),
    ("afd_editor", "task:update", "task", "task_team", None, True),
    ("team_editor", "task:delete", "task", "task_team", None, True),
    ("viewer", "task:update", "task", "task_team", None, False),
    ("afd_editor", "initiatief:update", "initiatief", "initiatief", None, True),
    ("team_editor", "initiatief:update", "initiatief", "initiatief", None, False),
    ("afd_editor", "lead:update", "lead", "lead", None, True),
    # creating: the eenheid it goes into
    ("afd_editor", "task:create", "task", None, "team", True),
    ("afd_editor", "task:create", "task", None, "directie", False),
    ("team_editor", "node:create", "corpus_node", None, "afdeling", False),
    # 5. tenant-wide fallbacks, only for resources without eenheid
    ("team_editor", "node:update", "corpus_node", "node_free", None, True),
    ("team_editor", "node:create", "corpus_node", None, None, True),
    ("viewer", "node:update", "corpus_node", "node_free", None, False),
    ("role_only", "node:update", "corpus_node", "node_free", None, False),
    ("team_editor", "lead:update", "lead", "lead_free", None, True),
    ("viewer", "lead:update", "lead", "lead_free", None, False),
    ("team_editor", "tag:create", "tag", None, None, True),
    ("team_editor", "people:create", "person", None, None, True),
    ("platform_admin", "people:create", "person", None, None, False),
    (
        "team_editor",
        "samenwerkingsverband:update",
        "samenwerkingsverband",
        "samenwerkingsverband",
        None,
        True,
    ),
    (
        "viewer",
        "samenwerkingsverband:update",
        "samenwerkingsverband",
        "samenwerkingsverband",
        None,
        False,
    ),
    (
        "manager",
        "samenwerkingsverband:delete",
        "samenwerkingsverband",
        "samenwerkingsverband",
        None,
        True,
    ),
    ("viewer", "tag:create", "tag", None, None, False),
    ("team_editor", "opdracht:update", "opdracht", "opdracht_free", None, True),
    ("viewer", "opdracht:update", "opdracht", "opdracht_free", None, False),
    ("team_editor", "opdracht:update", "opdracht", "opdracht_directie", None, False),
    ("manager", "opdracht:update", "opdracht", "opdracht_directie", None, True),
    ("team_editor", "opdracht:create", "opdracht", None, None, True),
    ("team_editor", "opdracht:create", "opdracht", None, "directie", False),
    # no tenant-wide fallback for initiatieven or team tasks
    ("team_editor", "task:create", "task", None, None, False),
    # org:update: a manager edits the eenheden below, editors do not
    ("manager", "org:update", "organisatie_eenheid", "eenheid_team", None, True),
    ("manager", "org:update", "organisatie_eenheid", "eenheid_elders", None, False),
    ("team_editor", "org:update", "organisatie_eenheid", "eenheid_team", None, False),
    ("super_admin", "org:update", "organisatie_eenheid", "eenheid_team", None, True),
]


@pytest.mark.parametrize("case", CASES, ids=[can_case_id(c) for c in CASES])
async def test_can(world, case):
    await assert_can_case(world, case)


@pytest.mark.parametrize(
    ("who", "eenheid", "expected"),
    [
        ("manager", "team", 200),
        ("team_editor", "team", 403),
        ("manager", "elders", 403),
    ],
)
async def test_route_update_eenheid_needs_org_update(world, who, eenheid, expected):
    """Editing an eenheid's attributes is org:update there, not a manager check."""
    url = f"/api/organisatie/{world.org[eenheid].id}"
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(url, json={"beschrijving": "Bijgewerkt"})
    assert resp.status_code == expected, resp.text


async def test_visible_is_not_writable(world):
    """A team editor sees the directie above the team, but cannot write there."""
    ctx = await perm_ctx(world, "team_editor")
    org_ctx = await build_org_context(
        world.db, world.person["team_editor"], perm_ctx=ctx
    )
    assert world.org["directie"].id in org_ctx.visible_eenheid_ids
    assert not await can(
        world.db, ctx, "node:update", "corpus_node", world.res["node_directie"]
    )


async def test_require_raises_404_403_401(world):
    ctx = await perm_ctx(world, "team_editor")
    with pytest.raises(HTTPException) as missing:
        await require(world.db, ctx, "node:update", "corpus_node", uuid.uuid4())
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as denied:
        await require(
            world.db, ctx, "node:update", "corpus_node", world.res["node_directie"]
        )
    assert denied.value.status_code == 403
    await require(world.db, ctx, "node:update", "corpus_node", world.res["node_team"])

    anonymous = PermissionContext(is_authenticated=False)
    with pytest.raises(HTTPException) as anon:
        await require(
            world.db, anonymous, "node:read", "corpus_node", world.res["node_free"]
        )
    assert anon.value.status_code == 401
    assert not await can(
        world.db, anonymous, "node:read", "corpus_node", world.res["node_free"]
    )


async def test_missing_resource_is_false_even_for_super_admin(world):
    ctx = await perm_ctx(world, "super_admin")
    assert not await can(world.db, ctx, "edge:update", "edge", uuid.uuid4())


@pytest.mark.parametrize(("level", "expected"), [("edit", True), ("read", False)])
async def test_edit_share_grants_write_with_own_rights(world, level, expected):
    """An edit share of the directie to the team lets team editors write there."""
    world.db.add(
        SharedAccess(
            source_eenheid_id=world.org["directie"].id,
            target_eenheid_id=world.org["team"].id,
            access_level=level,
            geldig_van=date.today(),
        )
    )
    await world.db.flush()
    editor = await perm_ctx(world, "team_editor")
    viewer = await perm_ctx(world, "viewer")
    node = world.res["node_directie"]
    assert await can(world.db, editor, "node:update", "corpus_node", node) is expected
    assert not await can(world.db, viewer, "node:update", "corpus_node", node)


# ---------------------------------------------------------------------------
# Reference routes: nodes, edges and tasks ask the same question
# ---------------------------------------------------------------------------


def _edge(from_key: str, to_key: str):
    return lambda w: {
        "from_node_id": str(w.res[from_key]),
        "to_node_id": str(w.res[to_key]),
        "edge_type_id": w.res["edge_type"],
    }


def _task(node_key: str, eenheid_key: str):
    return lambda w: {
        "title": "Taak",
        "node_id": str(w.res[node_key]),
        "organisatie_eenheid_id": str(w.org[eenheid_key].id),
    }


_MISSING = uuid.UUID("00000000-0000-4000-8000-000000000000")  # stable test ids
_NODE = {"title": "Nieuw", "node_type": "dossier", "status": "actief"}

ROUTES = [
    # nodes: rights on the node's eenheid; a missing node is 404
    ("viewer", "POST", "/api/nodes", _NODE, 403),
    ("viewer", "PUT", "/api/nodes/{node_team}", {"title": "Nee"}, 403),
    ("viewer", "DELETE", "/api/nodes/{node_team}", None, 403),
    ("team_editor", "PUT", "/api/nodes/{node_team}", {"title": "Ja"}, 200),
    ("team_editor", "PUT", "/api/nodes/{node_directie}", {"title": "Nee"}, 403),
    ("team_editor", "DELETE", "/api/nodes/{node_elders}", None, 403),
    ("team_editor", "PUT", f"/api/nodes/{_MISSING}", {"title": "?"}, 404),
    # edges: one writable end, the other end must be visible
    ("viewer", "POST", "/api/edges", _edge("node_team", "node_free"), 403),
    ("team_editor", "POST", "/api/edges", _edge("node_directie", "node_team"), 201),
    ("team_editor", "POST", "/api/edges", _edge("node_free", "node_team"), 201),
    ("team_editor", "POST", "/api/edges", _edge("node_afdeling", "node_directie"), 403),
    ("team_editor", "POST", "/api/edges", _edge("node_team", "node_elders"), 404),
    ("team_editor", "POST", "/api/edges", _edge("node_elders", "node_team"), 404),
    # tasks: the eenheid they go into, or are in
    ("viewer", "POST", "/api/tasks", _task("node_team", "team"), 403),
    ("afd_editor", "POST", "/api/tasks", _task("node_directie", "team"), 201),
    ("afd_editor", "POST", "/api/tasks", _task("node_team", "directie"), 403),
    ("team_editor", "POST", "/api/tasks", _task("node_team", "elders"), 403),
    (
        "afd_editor",
        "PUT",
        "/api/tasks/{task_team}",
        lambda w: {"organisatie_eenheid_id": str(w.org["directie"].id)},
        403,
    ),
    ("team_editor", "PUT", "/api/tasks/{task_team}", {"title": "Ja"}, 200),
    ("team_editor", "PUT", "/api/tasks/{task_elders}", {"title": "Nee"}, 403),
    ("team_editor", "DELETE", "/api/tasks/{task_elders}", None, 403),
    ("team_editor", "DELETE", f"/api/tasks/{_MISSING}", None, 404),
]  # fmt: skip


@pytest.mark.parametrize("case", ROUTES, ids=[route_case_id(c) for c in ROUTES])
async def test_routes(world, case):
    await assert_route_case(world, *case)


async def test_chat_write_tools_ask_authz(world):
    from bouwmeester.services.chat_service import _authorize_write_tool

    who = world.person["team_editor"].id
    refused = await _authorize_write_tool(
        "update_node",
        {"node_id": str(world.res["node_directie"]), "title": "Nee"},
        world.db,
        who,
    )
    allowed = await _authorize_write_tool(
        "update_node",
        {"node_id": str(world.res["node_team"]), "title": "Ja"},
        world.db,
        who,
    )
    edge_into_team = await _authorize_write_tool(
        "create_edge",
        {
            "from_node_id": str(world.res["node_directie"]),
            "to_node_id": str(world.res["node_team"]),
            "edge_type_id": "x",
        },
        world.db,
        who,
    )
    task_on_directie = await _authorize_write_tool(
        "create_task",
        {"node_id": str(world.res["node_directie"]), "title": "Nee"},
        world.db,
        who,
    )
    assert refused is not None
    assert allowed is None
    assert edge_into_team is None
    assert task_on_directie is not None
