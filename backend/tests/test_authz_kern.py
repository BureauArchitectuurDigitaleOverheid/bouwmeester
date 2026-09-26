# ruff: noqa: F811  (tests take the imported ``world`` fixture)
"""The decision point's core rules that routes rely on.

Builds on the tree of ``test_authz`` (``world``).  Covers:

- records linked from a request body must be usable by the caller;
- a task without eenheid is read through its node, in lists and details;
- an opdracht lives with its opdrachtgever and its opdrachtnemer-eenheid,
  and moving it needs rights on every eenheid that changes;
- stakeholder assessments are read where their scope is visible;
- synced eenheden are read-only, creating a (sub-)eenheid is free;
- reviewing a suggested edge is the reviewer's mandate on the item's node;
- linking a tag is editing the node;
- deciding a board or a node page costs a constant number of queries.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import event, select

from bouwmeester.core.authz import can
from bouwmeester.models.edge import Edge
from bouwmeester.models.lead import Lead
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.tag import Tag
from bouwmeester.models.task import Task
from tests.factories import client_as, grant_role, make_org, make_person, place
from tests.test_authz import World, _ctx, _node, world  # noqa: F401


def _ids(resp) -> set[str]:
    return {item["id"] for item in resp.json()}


# ---------------------------------------------------------------------------
# Records linked from a task body
# ---------------------------------------------------------------------------


async def _item(w: World, node_key: str | None = None) -> ParlementairItem:
    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-1",
        titel="Motie",
        onderwerp="Authz",
        bron="tweede_kamer",
        datum=date(2026, 1, 1),
        status="imported",
        corpus_node_id=w.res[node_key] if node_key else None,
    )
    w.db.add(item)
    await w.db.flush()
    return item


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
    item = await _item(world)
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


# ---------------------------------------------------------------------------
# A task without eenheid is read through its node
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("who", "sees"), [("viewer", False), ("afd_editor", True)])
async def test_task_without_eenheid_reads_through_its_node(world, who, sees):
    task = Task(title="Losse taak", node_id=world.res["node_sibling"], status="open")
    world.db.add(task)
    await world.db.flush()
    ctx = await _ctx(world, who)
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
    editor = await _ctx(world, "team_editor")
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
    manager = await _ctx(world, "manager")
    super_admin = await _ctx(world, "super_admin")
    assert not await can(
        world.db, manager, "org:update", "organisatie_eenheid", tooi.id
    )
    assert await can(
        world.db, super_admin, "org:update", "organisatie_eenheid", tooi.id
    )
    assert await can(world.db, manager, "org:read", "organisatie_eenheid", tooi.id)


def _ask(action: str, resource_type: str, resource_id=None, **props) -> dict:
    resource: dict = {"type": resource_type}
    if resource_id is not None:
        resource["id"] = str(resource_id)
    if props:
        resource["properties"] = {k: str(v) for k, v in props.items()}
    return {"action": action, "resource": resource}


@pytest.mark.parametrize(
    ("who", "expected"), [("team_editor", True), ("viewer", False)]
)
async def test_evaluation_answers_create_sub_eenheid(world, who, expected):
    ask = _ask("org:create", "organisatie_eenheid", eenheid_id=world.org["elders"].id)
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [ask]})
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
    admin = await make_person(world.db, "Ministeriebeheerder")
    await place(world.db, admin, world.org["directie"])
    await grant_role(world.db, admin, "ministry_admin", world.org["directie"])
    world.person["ministry_admin"] = admin
    item = await _item(world, item_node)
    edge_type = await world.db.scalar(
        select(Edge.edge_type_id).where(Edge.id == world.res["edge_team_directie"])
    )
    suggested = SuggestedEdge(
        parlementair_item_id=item.id,
        target_node_id=world.res[target],
        edge_type_id=edge_type,
        confidence=0.9,
    )
    world.db.add(suggested)
    await world.db.flush()
    ctx = await _ctx(world, who)
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


async def _evaluation_queries(world: World, who: str, asks: list[dict]) -> int:
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
    assert all(d["decision"] for d in resp.json()["evaluations"]), resp.json()
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
    few = [_ask("lead:update", "lead", i) for i in await _leads(world, 5)]
    many = [_ask("lead:update", "lead", i) for i in await _leads(world, 50)]
    assert await _evaluation_queries(world, who, many) == await _evaluation_queries(
        world, who, few
    )


async def _edges(world: World, n: int) -> list[uuid.UUID]:
    edge_type = await world.db.scalar(
        select(Edge.edge_type_id).where(Edge.id == world.res["edge_team_directie"])
    )
    team = world.org["team"]
    edges = []
    for i in range(n):
        other = await _node(world.db, f"Buur {i}", team)
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
    few = [_ask("edge:update", "edge", i) for i in await _edges(world, 5)]
    many = [_ask("edge:update", "edge", i) for i in await _edges(world, 50)]
    assert await _evaluation_queries(
        world, "team_editor", many
    ) == await _evaluation_queries(world, "team_editor", few)


async def test_edit_shares_are_looked_up_once_per_request(world):
    """Deciding many nodes asks for the caller's shares and placements once."""
    ctx = await _ctx(world, "team_editor")
    nodes = [
        await _node(world.db, f"Elders {i}", world.org["elders"]) for i in range(5)
    ]
    count = 0

    def _count(*_args):
        nonlocal count
        count += 1

    for node in nodes[:1]:
        await can(world.db, ctx, "node:update", "corpus_node", node.id)
    event.listen(world.db.sync_session, "do_orm_execute", _count)
    try:
        for node in nodes[1:]:
            await can(world.db, ctx, "node:update", "corpus_node", node.id)
    finally:
        event.remove(world.db.sync_session, "do_orm_execute", _count)
    # one locate per node, nothing else: rights and shares are cached
    assert count == len(nodes) - 1
