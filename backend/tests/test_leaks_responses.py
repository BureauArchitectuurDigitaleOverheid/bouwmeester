"""Responses must not name things the caller cannot read.

Uses ``world`` from ``tests/authz_world.py``.  The team members (``viewer``,
``team_editor``) and the afdeling editor see up their line but not
``Elders``, so ``Dossier elders`` and everything placed in ``Elders`` is
invisible to them.  Each test places a reference to something in ``Elders``
inside something they do read, and checks the response leaves it out.
"""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.models.lead_node import LeadNode
from bouwmeester.models.notification import Notification
from bouwmeester.models.opdracht import Opdracht, OpdrachtNode
from bouwmeester.models.parlementair_item import SuggestedEdge
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.task import Task
from tests.authz_world import World, make_item, make_node
from tests.factories import client_as, make_person

HIDDEN = "Dossier elders"


async def _get(w: World, who: str, url: str, **params):
    async with client_as(w.db, w.person[who]) as c:
        resp = await c.get(url, params=params)
    assert resp.status_code == 200, resp.text
    return resp


# ---------------------------------------------------------------------------
# M4: resources a person holds a role on
# ---------------------------------------------------------------------------


async def test_person_permissions_leave_out_unreadable_resources(world: World):
    world.db.add(
        ResourcePermission(
            person_id=world.person["role_only"].id,
            resource_type="corpus_node",
            resource_id=world.res["node_elders"],
            rol="betrokken",
        )
    )
    await world.db.flush()
    url = f"/api/resource-permissions/by-person/{world.person['role_only'].id}"

    seen = await _get(world, "viewer", url)
    names = {row["resource_name"] for row in seen.json()}
    assert "Directiedossier" in names
    assert HIDDEN not in seen.text

    full = await _get(world, "super_admin", url)
    assert HIDDEN in {row["resource_name"] for row in full.json()}


# ---------------------------------------------------------------------------
# M5: unassigned tasks without eenheid in the eenheid overview
# ---------------------------------------------------------------------------


async def test_eenheid_overview_counts_only_visible_tasks(world: World):
    world.db.add(Task(title="Losse taak elders", node_id=world.res["node_elders"]))
    await world.db.flush()

    resp = await _get(
        world,
        "viewer",
        "/api/tasks/eenheid-overview",
        organisatie_eenheid_id=world.org["team"].id,
    )
    body = resp.json()
    titles = {t["title"] for t in body["unassigned_no_unit"]}
    assert "Taak zonder eenheid" in titles
    assert "Losse taak elders" not in titles
    assert body["unassigned_no_unit_count"] == len(titles)


# ---------------------------------------------------------------------------
# M6: opdracht node koppelingen
# ---------------------------------------------------------------------------


async def test_create_opdracht_needs_read_on_every_koppeling(world: World):
    body = {
        "type": "opdracht",
        "titel": "Nieuwe opdracht",
        "begrotingsjaar": 2026,
        "instrument_id": str(world.res["node_afdeling"]),
        "opdrachtgever_id": str(world.org["afdeling"].id),
        "node_koppelingen": [{"node_id": str(world.res["node_elders"])}],
    }
    async with client_as(world.db, world.person["afd_editor"]) as c:
        refused = await c.post("/api/opdrachten", json=body)
        body["node_koppelingen"] = [{"node_id": str(world.res["node_team"])}]
        allowed = await c.post("/api/opdrachten", json=body)
    assert refused.status_code == 404, refused.text
    assert allowed.status_code == 201, allowed.text


async def test_opdracht_responses_leave_out_unreadable_nodes(world: World):
    opdracht_id = world.res["opdracht_directie"]
    opdracht = await world.db.get(Opdracht, opdracht_id)
    opdracht.instrument_id = world.res["node_elders"]
    world.db.add_all(
        [
            OpdrachtNode(opdracht_id=opdracht_id, node_id=world.res["node_elders"]),
            OpdrachtNode(opdracht_id=opdracht_id, node_id=world.res["node_team"]),
        ]
    )
    await world.db.flush()
    world.db.expire(opdracht)

    detail = await _get(world, "viewer", f"/api/opdrachten/{opdracht_id}")
    listed = await _get(
        world, "viewer", f"/api/nodes/{world.res['node_team']}/opdrachten"
    )
    for body in (detail.json(), listed.json()[0]):
        assert [k["node_title"] for k in body["node_koppelingen"]] == ["Teamdossier"]
        assert body["instrument"] is None
    assert HIDDEN not in detail.text + listed.text

    full = await _get(world, "super_admin", f"/api/opdrachten/{opdracht_id}")
    assert full.json()["instrument"]["title"] == HIDDEN


# ---------------------------------------------------------------------------
# M7 / L3: a task's subtasks, opdracht and node
# ---------------------------------------------------------------------------


@pytest.fixture
async def task_refs(world: World) -> World:
    """``task_team`` gets a visible and a hidden subtask and a hidden opdracht."""
    elders_opdracht = Opdracht(
        type="opdracht",
        titel="Opdracht elders",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["elders"].id,
    )
    world.db.add(elders_opdracht)
    await world.db.flush()
    task = await world.db.get(Task, world.res["task_team"])
    task.opdracht_id = elders_opdracht.id
    visible = Task(
        title="Zichtbare subtaak",
        node_id=world.res["node_team"],
        organisatie_eenheid_id=world.org["team"].id,
        parent_id=task.id,
    )
    hidden = Task(
        title="Subtaak elders",
        node_id=world.res["node_elders"],
        organisatie_eenheid_id=world.org["elders"].id,
        parent_id=task.id,
    )
    world.db.add_all([visible, hidden])
    await world.db.flush()
    world.res.update(subtask_visible=visible.id, subtask_hidden=hidden.id)
    return world


def _assert_redacted(task: dict) -> None:
    assert [s["title"] for s in task["subtasks"]] == ["Zichtbare subtaak"]
    assert task["opdracht"] is None


async def test_task_responses_leave_out_unreadable_subtasks_and_opdracht(
    task_refs: World,
):
    w = task_refs
    task_id = str(w.res["task_team"])
    detail = await _get(w, "viewer", f"/api/tasks/{task_id}")
    _assert_redacted(detail.json())

    for url, params in (
        (f"/api/nodes/{w.res['node_directie']}/tasks", {}),
        ("/api/tasks", {"organisatie_eenheid_id": w.org["team"].id}),
        ("/api/tasks", {}),
    ):
        resp = await _get(w, "viewer", url, **params)
        [task] = [t for t in resp.json() if t["id"] == task_id]
        _assert_redacted(task)
        assert "Subtaak elders" not in resp.text
        assert "Opdracht elders" not in resp.text

    full = await _get(w, "super_admin", f"/api/tasks/{task_id}")
    assert len(full.json()["subtasks"]) == 2
    assert full.json()["opdracht"]["titel"] == "Opdracht elders"


async def test_eenheid_overview_redacts_embedded_tasks(task_refs: World):
    w = task_refs
    task = await w.db.get(Task, w.res["task_team"])
    task.assignee_id = None
    await w.db.flush()
    resp = await _get(
        w,
        "viewer",
        "/api/tasks/eenheid-overview",
        organisatie_eenheid_id=w.org["team"].id,
    )
    [embedded] = [
        t
        for t in resp.json()["unassigned_no_person"]
        if t["id"] == str(w.res["task_team"])
    ]
    _assert_redacted(embedded)


async def test_own_task_on_unreadable_node_hides_the_node(world: World):
    world.db.add(
        Task(
            title="Mijn taak elders",
            node_id=world.res["node_elders"],
            organisatie_eenheid_id=world.org["elders"].id,
            assignee_id=world.person["viewer"].id,
        )
    )
    await world.db.flush()
    resp = await _get(world, "viewer", "/api/tasks/my")
    [task] = [t for t in resp.json() if t["title"] == "Mijn taak elders"]
    assert task["node"] is None
    assert task["node_id"] == str(world.res["node_elders"])
    assert HIDDEN not in resp.text


# ---------------------------------------------------------------------------
# L2: reordering subtasks
# ---------------------------------------------------------------------------


async def test_reorder_subtasks_covers_only_visible_ones(task_refs: World):
    w = task_refs
    url = f"/api/tasks/{w.res['task_team']}/subtasks/reorder"
    async with client_as(w.db, w.person["team_editor"]) as c:
        ok = await c.put(url, json={"task_ids": [str(w.res["subtask_visible"])]})
        both = await c.put(
            url,
            json={
                "task_ids": [
                    str(w.res["subtask_visible"]),
                    str(w.res["subtask_hidden"]),
                ]
            },
        )
        empty = await c.put(url, json={"task_ids": []})
    assert ok.status_code == 200, ok.text
    assert [t["title"] for t in ok.json()] == ["Zichtbare subtaak"]
    # A hidden subtask is not one of "your" subtasks, and the message tells
    # nothing about how many there are.
    for refused in (both, empty):
        assert refused.status_code == 400, refused.text
        assert str(w.res["subtask_hidden"]) not in refused.text
        assert "1" not in refused.json()["detail"]
        assert "2" not in refused.json()["detail"]


# ---------------------------------------------------------------------------
# L3: lead detail linked nodes
# ---------------------------------------------------------------------------


async def test_lead_detail_leaves_out_unreadable_linked_nodes(world: World):
    world.db.add_all(
        [
            LeadNode(lead_id=world.res["lead"], node_id=world.res["node_elders"]),
            LeadNode(lead_id=world.res["lead"], node_id=world.res["node_afdeling"]),
        ]
    )
    await world.db.flush()
    resp = await _get(world, "afd_editor", f"/api/leads/{world.res['lead']}")
    titles = [n["node_title"] for n in resp.json()["linked_nodes"]]
    assert titles == ["Afdelingsdossier"]
    assert HIDDEN not in resp.text


# ---------------------------------------------------------------------------
# L4: changing a grant on something you cannot see
# ---------------------------------------------------------------------------


async def test_last_owner_rule_does_not_answer_outsiders(world: World):
    owner = await make_person(world.db, "Eigenaar elders")
    grant = ResourcePermission(
        person_id=owner.id,
        resource_type="corpus_node",
        resource_id=world.res["node_elders"],
        rol="eigenaar",
    )
    world.db.add(grant)
    await world.db.flush()
    async with client_as(world.db, world.person["team_editor"]) as c:
        deleted = await c.delete(f"/api/resource-permissions/{grant.id}")
        updated = await c.put(
            f"/api/resource-permissions/{grant.id}", json={"rol": "betrokken"}
        )
    assert deleted.status_code == 404, deleted.text
    assert updated.status_code == 404, updated.text


# ---------------------------------------------------------------------------
# L5 / L9: suggested edges
# ---------------------------------------------------------------------------


@pytest.fixture
async def suggestion(world: World) -> World:
    """A suggestion from an item on the team node to the hidden node."""
    item = await make_item(world, "node_team")
    edge = SuggestedEdge(
        parlementair_item_id=item.id,
        target_node_id=world.res["node_elders"],
        edge_type_id=world.res["edge_type"],
        confidence=0.9,
        reason="Gaat over Dossier elders",
    )
    world.db.add(edge)
    await world.db.flush()
    world.res["suggested_edge"] = edge.id
    return world


async def test_suggestion_response_blanks_an_unreadable_target(suggestion: World):
    w = suggestion
    async with client_as(w.db, w.person["team_editor"]) as c:
        resp = await c.put(f"/api/parlementair/edges/{w.res['suggested_edge']}/reject")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_node"] is None
    assert body["target_node_id"] is None
    assert body["reason"] is None
    assert str(w.res["node_elders"]) not in resp.text


@pytest.fixture
async def visible_suggestion(world: World) -> World:
    """A suggestion from an item on the team node to the directie node."""
    item = await make_item(world, "node_team")
    edge = SuggestedEdge(
        parlementair_item_id=item.id,
        target_node_id=world.res["node_afdeling"],
        edge_type_id=world.res["edge_type"],
        confidence=0.9,
    )
    world.db.add(edge)
    await world.db.flush()
    world.res["suggested_edge"] = edge.id
    return world


async def test_approving_twice_is_a_conflict(visible_suggestion: World):
    w = visible_suggestion
    url = f"/api/parlementair/edges/{w.res['suggested_edge']}"
    async with client_as(w.db, w.person["team_editor"]) as c:
        first = await c.put(f"{url}/approve")
        second = await c.put(f"{url}/approve")
    assert first.status_code == 200, first.text
    assert first.json()["target_node_id"] == str(w.res["node_afdeling"])
    assert second.status_code == 409, second.text
    edges = await w.db.scalars(
        select(Edge).where(
            Edge.from_node_id == w.res["node_team"],
            Edge.to_node_id == w.res["node_afdeling"],
        )
    )
    assert len(edges.all()) == 1


async def test_rejected_suggestion_is_reopened_before_approval(
    visible_suggestion: World,
):
    w = visible_suggestion
    url = f"/api/parlementair/edges/{w.res['suggested_edge']}"
    async with client_as(w.db, w.person["team_editor"]) as c:
        rejected = await c.put(f"{url}/reject")
        approve = await c.put(f"{url}/approve")
        reset = await c.put(f"{url}/reset")
        approved = await c.put(f"{url}/approve")
    assert rejected.status_code == 200, rejected.text
    assert approve.status_code == 409, approve.text
    assert reset.status_code == 200, reset.text
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


async def test_approved_suggestion_is_not_rejected_directly(
    visible_suggestion: World,
):
    w = visible_suggestion
    url = f"/api/parlementair/edges/{w.res['suggested_edge']}"
    async with client_as(w.db, w.person["team_editor"]) as c:
        await c.put(f"{url}/approve")
        rejected = await c.put(f"{url}/reject")
    assert rejected.status_code == 409, rejected.text


# ---------------------------------------------------------------------------
# L6: community graph
# ---------------------------------------------------------------------------


@pytest.fixture
async def community(world: World) -> World:
    lead_id = world.res["lead"]
    world.db.add_all(
        [
            ResourcePermission(
                person_id=world.person["viewer"].id,
                resource_type="lead",
                resource_id=lead_id,
                rol="contactpersoon",
            ),
            ResourcePermission(
                organisatie_eenheid_id=world.org["team"].id,
                resource_type="lead",
                resource_id=lead_id,
                rol="betrokken",
            ),
        ]
    )
    await world.db.flush()
    return world


async def test_community_graph_needs_people_read_for_people(community: World):
    w = community
    params = {"initiatief_id": w.res["initiatief"]}
    # role_only reads the initiatief as contributor but holds no people:read.
    hidden = await _get(w, "role_only", "/api/graph/community", **params)
    assert not [n for n in hidden.json()["nodes"] if n["node_type"] == "person"]
    assert "Teamlid" not in hidden.text

    shown = await _get(w, "afd_editor", "/api/graph/community", **params)
    assert "Teamlid" in shown.text


async def test_community_graph_draws_eenheid_grants_to_the_eenheid(community: World):
    w = community
    resp = await _get(
        w,
        "afd_editor",
        "/api/graph/community",
        initiatief_id=w.res["initiatief"],
    )
    body = resp.json()
    ids = {n["id"] for n in body["nodes"]}
    assert "person-None" not in resp.text
    for edge in body["edges"]:
        assert edge["source"] in ids and edge["target"] in ids, edge
    team_key = f"oe-{w.org['team'].id}"
    assert any(
        e["source"] == f"lead-{w.res['lead']}" and e["target"] == team_key
        for e in body["edges"]
    )


# ---------------------------------------------------------------------------
# L7: beleidskompas progress and gap analysis
# ---------------------------------------------------------------------------


@pytest.fixture
async def kompas(world: World) -> World:
    """The team dossier has a visible probleem and a doel in Elders."""
    if await world.db.get(EdgeType, "onderdeel_van") is None:
        world.db.add(EdgeType(id="onderdeel_van", label_nl="O", label_en="P"))
        await world.db.flush()
    probleem = await make_node(world.db, "Probleem", world.org["team"])
    probleem.node_type = "probleem"
    doel = await make_node(world.db, "Doel elders", world.org["elders"])
    doel.node_type = "doel"
    for child in (probleem, doel):
        world.db.add(
            Edge(
                from_node_id=child.id,
                to_node_id=world.res["node_team"],
                edge_type_id="onderdeel_van",
            )
        )
    await world.db.flush()
    return world


async def test_beleidskompas_progress_counts_only_visible_children(kompas: World):
    w = kompas

    async def progress(who: str) -> int:
        resp = await _get(w, who, "/api/nodes", node_type="dossier", limit=500)
        [node] = [n for n in resp.json() if n["id"] == str(w.res["node_team"])]
        return node["beleidskompas_progress"]["completed_steps"]

    assert await progress("viewer") == 1
    assert await progress("super_admin") == 2


async def test_gap_analysis_counts_only_visible_children(kompas: World):
    w = kompas

    async def completed(who: str) -> tuple[int, int]:
        async with client_as(w.db, w.person[who]) as c:
            gap = await c.post(
                "/api/llm/gap-analysis",
                json={"dossier_id": str(w.res["node_team"])},
            )
            overview = await c.get("/api/llm/corpus-gaps")
        assert gap.status_code == 200, gap.text
        [item] = [
            i
            for i in overview.json()["items"]
            if i["dossier_id"] == str(w.res["node_team"])
        ]
        return gap.json()["completed_count"], item["completed_count"]

    assert await completed("viewer") == (1, 1)
    assert await completed("super_admin") == (2, 2)


# ---------------------------------------------------------------------------
# L13: the sender of a mention in a task is the caller
# ---------------------------------------------------------------------------


async def test_task_mention_sender_is_the_caller(world: World):
    mentioned = world.person["afd_editor"]
    body = {
        "title": f"Taak {uuid.uuid4().hex[:6]}",
        "description": f"Zie [@Redacteur](user:{mentioned.id})",
        "node_id": str(world.res["node_team"]),
        "organisatie_eenheid_id": str(world.org["team"].id),
        "assignee_id": str(world.person["viewer"].id),
    }
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post("/api/tasks", json=body)
    assert resp.status_code == 201, resp.text
    notification = await world.db.scalar(
        select(Notification).where(
            Notification.person_id == mentioned.id,
            Notification.type == "mention",
        )
    )
    assert notification is not None
    assert notification.sender_id == world.person["team_editor"].id
