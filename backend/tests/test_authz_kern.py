"""The decision point's core rules that routes rely on.

Uses ``world`` from ``tests/authz_world.py``.  Covers:

- records linked from a request body must be usable by the caller;
- a task without eenheid is read through its node, in lists and details;
- an opdracht lives with its opdrachtgever and its opdrachtnemer-eenheid,
  and moving it needs rights on every eenheid that changes;
- stakeholder assessments are read where their scope is visible;
- synced eenheden are read-only, creating a (sub-)eenheid is free;
- reviewing a suggested edge is the reviewer's mandate on the item's node;
- linking a tag is editing the node;
- the evaluation endpoint decides a board or a node page in a constant
  number of queries.
"""

import uuid

import pytest
from sqlalchemy import event

from bouwmeester.core.authz import can
from bouwmeester.models.edge import Edge
from bouwmeester.models.lead import Lead
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.parlementair_item import SuggestedEdge
from bouwmeester.models.tag import Tag
from bouwmeester.models.task import Task
from tests.authz_world import (
    World,
    add_directie_admin,
    ask,
    make_item,
    make_node,
    perm_ctx,
)
from tests.factories import client_as, make_org


def _ids(resp) -> set[str]:
    return {item["id"] for item in resp.json()}


# ---------------------------------------------------------------------------
# Records linked from a task body
# ---------------------------------------------------------------------------


@pytest.fixture
async def links(world: World) -> dict[str, uuid.UUID]:
    db = world.db
    opdracht_elders = Opdracht(
        type="opdracht",
        titel="Elders",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["elders"].id,
    )
    task_directie = Task(
        title="Directietaak",
        node_id=world.res["node_directie"],
        organisatie_eenheid_id=world.org["directie"].id,
        status="open",
    )
    db.add_all([opdracht_elders, task_directie])
    await db.flush()
    item = await make_item(world)
    return {
        "opdracht_elders": opdracht_elders.id,
        "task_directie": task_directie.id,
        "item": item.id,
    }


def _task(world: World, **extra) -> dict:
    return {
        "title": "Taak",
        "node_id": str(world.res["node_team"]),
        "organisatie_eenheid_id": str(world.org["team"].id),
        **{k: str(v) for k, v in extra.items()},
    }


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({}, 201),
        ({"node_id": "node_sibling"}, 404),  # a node you do not see
        ({"opdracht_id": "opdracht_elders"}, 404),  # an opdracht you do not see
        ({"opdracht_id": "opdracht_directie"}, 201),  # one you see
        ({"parent_id": "task_team"}, 201),  # a parent you may update
        ({"parent_id": "task_directie"}, 403),  # one you may only see
        ({"parlementair_item_id": "item"}, 201),
        ({"parlementair_item_id": "missing"}, 404),
    ],
    ids=lambda v: str(v) if isinstance(v, int) else "-".join(v.values()) or "plain",
)
async def test_task_body_links_are_checked(world, links, extra, expected):
    lookup = {**world.res, **links, "missing": uuid.uuid4()}
    body = _task(world, **{k: lookup[v] for k, v in extra.items()})
    async with client_as(world.db, world.person["team_editor"]) as c:
        created = await c.post("/api/tasks", json=body)
        updated = await c.put(
            f"/api/tasks/{world.res['task_team']}",
            json={k: body[k] for k in extra},
        )
    assert created.status_code == expected, created.text
    assert updated.status_code == (200 if expected == 201 else expected), updated.text


async def test_linking_a_node_to_a_lead_needs_seeing_it(world):
    lead = world.res["lead_free"]
    async with client_as(world.db, world.person["team_editor"]) as c:
        hidden = await c.post(
            f"/api/leads/{lead}/nodes",
            json={"node_id": str(world.res["node_sibling"])},
        )
        visible = await c.post(
            f"/api/leads/{lead}/nodes", json={"node_id": str(world.res["node_team"])}
        )
    assert hidden.status_code == 404, hidden.text
    assert visible.status_code == 201, visible.text


async def test_node_detail_leaves_out_edges_to_hidden_nodes(world):
    """The viewer sees the directie above the team, not the eenheid elders."""
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.get(f"/api/nodes/{world.res['node_directie']}")
    async with client_as(world.db, world.person["super_admin"]) as c:
        admin = await c.get(f"/api/nodes/{world.res['node_directie']}")
    edges = {e["id"] for e in resp.json()["edges_from"] + resp.json()["edges_to"]}
    assert edges == {str(world.res["edge_team_directie"])}
    assert resp.json()["edge_count"] == 1
    assert admin.json()["edge_count"] == 2


# ---------------------------------------------------------------------------
# A task without eenheid is read through its node
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("who", "sees"), [("viewer", False), ("afd_editor", True)])
async def test_task_without_eenheid_reads_through_its_node(world, who, sees):
    task = Task(title="Losse taak", node_id=world.res["node_sibling"], status="open")
    world.db.add(task)
    await world.db.flush()
    ctx = await perm_ctx(world, who)
    async with client_as(world.db, world.person[who]) as c:
        detail = await c.get(f"/api/tasks/{task.id}")
        listing = await c.get("/api/tasks", params={"limit": 500})
    assert await can(world.db, ctx, "task:read", "task", task.id) is sees
    assert detail.status_code == (200 if sees else 404), detail.text
    assert (str(task.id) in _ids(listing)) is sees


# ---------------------------------------------------------------------------
# Opdrachten: two eenheden
# ---------------------------------------------------------------------------


async def test_opdracht_lives_with_its_opdrachtnemer_too(world):
    opdracht = Opdracht(
        type="opdracht",
        titel="Uitvoering door het team",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["elders"].id,
        opdrachtnemer_eenheid_id=world.org["team"].id,
    )
    world.db.add(opdracht)
    await world.db.flush()
    editor = await perm_ctx(world, "team_editor")
    async with client_as(world.db, world.person["viewer"]) as c:
        detail = await c.get(f"/api/opdrachten/{opdracht.id}")
        listing = await c.get("/api/opdrachten", params={"limit": 500})
    assert detail.status_code == 200, detail.text
    assert str(opdracht.id) in _ids(listing)
    assert await can(world.db, editor, "opdracht:update", "opdracht", opdracht.id)


@pytest.mark.parametrize(
    ("who", "change", "expected"),
    [
        ("manager", {"opdrachtgever_id": "team"}, 200),  # below the directie
        ("manager", {"opdrachtgever_id": "elders"}, 403),  # no rights there
        ("manager", {"opdrachtnemer_eenheid_id": "elders"}, 403),
        ("manager", {"opdrachtgever_id": None}, 403),  # unscoping: system only
        ("super_admin", {"opdrachtgever_id": None}, 200),
        ("afd_editor", {"opdrachtgever_id": "team"}, 403),  # not on the old one
    ],
)
async def test_rescoping_an_opdracht_needs_every_changed_eenheid(
    world, who, change, expected
):
    body = {k: str(world.org[v].id) if v else None for k, v in change.items()}
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.put(
            f"/api/opdrachten/{world.res['opdracht_directie']}", json=body
        )
    assert resp.status_code == expected, resp.text


# ---------------------------------------------------------------------------
# Stakeholder assessments
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope_type", "scope", "expected"),
    [
        ("corpus_node", "node_team", 200),
        ("corpus_node", "node_sibling", 404),  # the corpus follows visibility
        ("corpus_node", "missing", 404),
        ("initiatief", "initiatief", 200),
    ],
)
async def test_assessments_are_read_where_the_scope_is_visible(
    world, scope_type, scope, expected
):
    scope_id = world.res.get(scope, uuid.uuid4())
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.get(
            "/api/stakeholder-assessments",
            params={"scope_type": scope_type, "scope_id": str(scope_id)},
        )
    assert resp.status_code == expected, resp.text


# ---------------------------------------------------------------------------
# Eenheden: synced ones are read-only, creating is free
# ---------------------------------------------------------------------------


async def test_synced_eenheid_is_read_only_in_authz(world):
    tooi = await make_org(world.db, "TOOI-team", "team", world.org["directie"])
    tooi.bron = "tooi"
    await world.db.flush()
    manager = await perm_ctx(world, "manager")
    super_admin = await perm_ctx(world, "super_admin")
    assert not await can(
        world.db, manager, "org:update", "organisatie_eenheid", tooi.id
    )
    assert await can(
        world.db, super_admin, "org:update", "organisatie_eenheid", tooi.id
    )
    assert await can(world.db, manager, "org:read", "organisatie_eenheid", tooi.id)


@pytest.mark.parametrize(
    ("who", "expected"), [("team_editor", True), ("viewer", False)]
)
async def test_evaluation_answers_create_sub_eenheid(world, who, expected):
    question = ask(
        "org:create", "organisatie_eenheid", eenheid_id=world.org["elders"].id
    )
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [question]})
        created = await c.post(
            "/api/organisatie",
            json={
                "naam": "Stakeholder",
                "type": "directie",
                "parent_id": str(world.org["elders"].id),
            },
        )
    assert resp.json() == {"evaluations": [{"decision": expected}]}
    assert created.status_code == (201 if expected else 403), created.text


# ---------------------------------------------------------------------------
# Suggested edges: reviewing is the reviewer's mandate on the item's node
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "item_node", "target", "expected"),
    [
        ("ministry_admin", "node_team", "node_elders", True),  # below its directie
        ("ministry_admin", "node_elders", "node_team", False),
        ("team_editor", "node_team", "node_directie", True),
        # editing the target end is no mandate to review the item
        ("team_editor", "node_directie", "node_team", False),
        ("viewer", "node_team", "node_team", False),
        ("team_editor", None, "node_team", True),  # an item without node yet
    ],
)
async def test_suggested_edge_review_is_on_the_item_node(
    world, who, item_node, target, expected
):
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    item = await make_item(world, item_node)
    suggested = SuggestedEdge(
        parlementair_item_id=item.id,
        target_node_id=world.res[target],
        edge_type_id=world.res["edge_type"],
        confidence=0.9,
    )
    world.db.add(suggested)
    await world.db.flush()
    ctx = await perm_ctx(world, who)
    for verb in ("update", "delete"):
        got = await can(
            world.db, ctx, f"suggested_edge:{verb}", "suggested_edge", suggested.id
        )
        assert got is expected, verb


# ---------------------------------------------------------------------------
# Tags on nodes
# ---------------------------------------------------------------------------


async def test_linking_a_tag_is_editing_the_node(world):
    """role_only edits node_directie (betrokken) but holds no tag:create."""
    world.db.add(Tag(name="Bestaand label"))
    await world.db.flush()
    url = f"/api/nodes/{world.res['node_directie']}/tags"
    async with client_as(world.db, world.person["role_only"]) as c:
        existing = await c.post(url, json={"tag_name": "Bestaand label"})
        new = await c.post(url, json={"tag_name": "Nieuw label"})
    async with client_as(world.db, world.person["team_editor"]) as c:
        not_editor = await c.post(url, json={"tag_name": "Bestaand label"})
    assert existing.status_code == 201, existing.text
    assert new.status_code == 403, new.text
    assert not_editor.status_code == 403, not_editor.text


# ---------------------------------------------------------------------------
# Query counts: a board and a node page cost the same for 5 or 50 items
# ---------------------------------------------------------------------------


async def _evaluation_queries(
    world: World, who: str, asks: list[dict], expected: bool = True
) -> int:
    count = 0

    def _count(*_args):
        nonlocal count
        count += 1

    async with client_as(world.db, world.person[who]) as c:
        event.listen(world.db.sync_session, "do_orm_execute", _count)
        try:
            resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
        finally:
            event.remove(world.db.sync_session, "do_orm_execute", _count)
    assert resp.status_code == 200, resp.text
    decisions = {d["decision"] for d in resp.json()["evaluations"]}
    assert decisions == {expected}, resp.json()
    return count


async def _leads(world: World, n: int) -> list[uuid.UUID]:
    leads = [
        Lead(
            title=f"Lead {i}", stage="verkennen", initiatief_id=world.res["initiatief"]
        )
        for i in range(n)
    ]
    world.db.add_all(leads)
    await world.db.flush()
    return [lead.id for lead in leads]


@pytest.mark.parametrize("who", ["role_only", "afd_editor"])
async def test_board_evaluation_costs_constant_queries(world, who):
    few = [ask("lead:update", "lead", i) for i in await _leads(world, 5)]
    many = [ask("lead:update", "lead", i) for i in await _leads(world, 50)]
    assert await _evaluation_queries(world, who, many) == await _evaluation_queries(
        world, who, few
    )


async def _edges(world: World, n: int) -> list[uuid.UUID]:
    edge_type = world.res["edge_type"]
    team = world.org["team"]
    edges = []
    for i in range(n):
        other = await make_node(world.db, f"Buur {i}", team)
        edges.append(
            Edge(
                from_node_id=world.res["node_team"],
                to_node_id=other.id,
                edge_type_id=edge_type,
            )
        )
    world.db.add_all(edges)
    await world.db.flush()
    return [edge.id for edge in edges]


async def test_node_page_evaluation_costs_constant_queries(world):
    few = [ask("edge:update", "edge", i) for i in await _edges(world, 5)]
    many = [ask("edge:update", "edge", i) for i in await _edges(world, 50)]
    assert await _evaluation_queries(
        world, "team_editor", many
    ) == await _evaluation_queries(world, "team_editor", few)


async def _nodes_elders(world: World, n: int) -> list[uuid.UUID]:
    return [
        (await make_node(world.db, f"Elders {i}", world.org["elders"])).id
        for i in range(n)
    ]


async def test_refused_node_evaluation_costs_constant_queries(world):
    """A refusal walks every step (edit shares, placements) once per request."""
    few = [ask("node:update", "corpus_node", i) for i in await _nodes_elders(world, 5)]
    many = [
        ask("node:update", "corpus_node", i) for i in await _nodes_elders(world, 50)
    ]
    assert await _evaluation_queries(
        world, "team_editor", many, expected=False
    ) == await _evaluation_queries(world, "team_editor", few, expected=False)
