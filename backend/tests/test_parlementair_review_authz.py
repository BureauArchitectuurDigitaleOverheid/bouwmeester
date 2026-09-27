"""Reviewing a parliamentary item is decided on the item's node.

Uses ``world`` from ``tests/authz_world.py``; ``pw`` adds a ministry_admin
scoped to the directie, who reviews there but writes no nodes.  A reviewer
approves a suggestion whatever its target; a target they cannot read is
left out of every answer.
"""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import can
from bouwmeester.models.edge import Edge
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.task import Task
from bouwmeester.services.parlementair_import_service import (
    ParlementairImportService,
)
from tests.authz_world import (
    World,
    add,
    add_directie_admin,
    ask,
    evaluate,
    make_item,
    make_node,
    perm_ctx,
    request,
    rp,
)
from tests.factories import make_person, place


@pytest.fixture
async def pw(world: World) -> World:
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    return world


async def _suggest(
    w: World, item: ParlementairItem, target: str, **kw
) -> SuggestedEdge:
    return await add(
        w,
        SuggestedEdge(
            parlementair_item_id=item.id,
            target_node_id=w.res[target],
            edge_type_id=w.res["edge_type"],
            confidence=0.9,
            **kw,
        ),
    )


async def _item_on_fresh_node(w: World) -> ParlementairItem:
    """An imported item on a new node without eenheid, as the import makes it."""
    node = await make_node(w.db, "Motie")
    node.node_type = "politieke_input"
    item = await make_item(w)
    item.corpus_node_id = node.id
    await w.db.flush()
    return item


# (who, node of the item, expected status of PUT .../reject)
REVIEW_CASES = [
    ("team_editor", "node_team", 200),
    ("afd_editor", "node_team", 200),  # a role applies to everything below
    ("team_editor", "node_directie", 403),  # visible above, not writable
    ("manager", "node_elders", 404),  # not visible: as if it did not exist
    ("team_editor", "node_free", 200),  # a node without eenheid is tenant-wide
    ("viewer", "node_free", 403),  # viewers do not review
    ("team_editor", None, 200),  # no node yet: like a new node without eenheid
]  # fmt: skip


@pytest.mark.parametrize(("who", "node", "expected"), REVIEW_CASES)
async def test_review_is_decided_on_the_item_node(world, who, node, expected):
    item = await make_item(world, node)
    resp = await request(
        world, who, "PUT", f"/api/parlementair/imports/{item.id}/reject"
    )
    assert resp.status_code == expected, resp.text


# (who, item node, target node, may review the suggestion?, approve too?).
# Editing the target end is no mandate; approving needs no edge:create.
SUGGESTION_CASES = [
    ("ministry_admin", "node_team", "node_elders", True, False),  # below directie
    ("ministry_admin", "node_elders", "node_team", False, False),
    ("ministry_admin", "node_directie", "node_team", True, True),
    ("team_editor", "node_team", "node_directie", True, False),
    ("team_editor", "node_team", "node_elders", True, True),  # target out of reach
    ("team_editor", "node_directie", "node_team", False, False),
    ("team_editor", "node_free", "node_team", True, True),
    ("viewer", "node_team", "node_team", False, False),
    ("team_editor", None, "node_team", True, False),  # an item without node yet
]  # fmt: skip


@pytest.mark.parametrize(
    ("who", "node", "target", "allowed", "approve"), SUGGESTION_CASES
)
async def test_suggestion_review_is_the_reviewers_mandate(
    pw, who, node, target, allowed, approve
):
    item = await make_item(pw, node)
    suggested = await _suggest(pw, item, target)
    other = await _suggest(pw, item, "node_afdeling")
    ctx = await perm_ctx(pw, who)
    for verb in ("update", "delete"):
        got = await can(
            pw.db, ctx, f"suggested_edge:{verb}", "suggested_edge", suggested.id
        )
        assert got is allowed, verb
    if approve:
        url = "/api/parlementair/edges"
        approved = await request(pw, who, "PUT", f"{url}/{suggested.id}/approve")
        # rejecting creates nothing: reviewing the item is enough
        reject = await request(pw, who, "PUT", f"{url}/{other.id}/reject")
        assert (approved.status_code, reject.status_code) == (200, 200)


async def test_suggestion_status_moves_one_way(world):
    """Approved once; rejected only after a reset; never approved twice."""
    item = await make_item(world, "node_team")
    first = await _suggest(world, item, "node_afdeling")
    second = await _suggest(world, item, "node_free")

    async def put(suggestion, action):
        url = f"/api/parlementair/edges/{suggestion.id}/{action}"
        return (await request(world, "team_editor", "PUT", url)).status_code

    assert await put(first, "approve") == 200
    assert [await put(first, "approve"), await put(first, "reject")] == [409, 409]
    edges = await world.db.scalars(
        select(Edge).where(
            Edge.from_node_id == world.res["node_team"],
            Edge.to_node_id == world.res["node_afdeling"],
        )
    )
    assert len(edges.all()) == 1
    steps = ["reject", "approve", "reset", "approve"]
    assert [await put(second, s) for s in steps] == [200, 409, 200, 200]
    await world.db.refresh(second)
    assert second.status == "approved"


@pytest.mark.parametrize(
    ("method", "action"),
    [("PUT", "reject"), ("PUT", "reset"), ("PATCH", ""), ("PUT", "approve")],
)
@pytest.mark.parametrize(
    ("target", "shown"), [("node_elders", False), ("node_afdeling", True)]
)
async def test_suggestion_action_hides_an_unreadable_target(
    world, method, action, target, shown
):
    item = await make_item(world, "node_team")
    reason = "Gaat over Dossier elders"
    suggested = await _suggest(world, item, target, reason=reason)
    url = f"/api/parlementair/edges/{suggested.id}" + (f"/{action}" if action else "")
    body = {"edge_type_id": world.res["edge_type"]} if method == "PATCH" else None
    resp = await request(world, "team_editor", method, url, body)
    assert resp.status_code == 200, resp.text
    got = resp.json()
    assert (got["target_node"] is not None) is shown
    if not shown:
        assert got["target_node_id"] is None and got["reason"] is None
        assert str(world.res[target]) not in resp.text


async def test_item_views_hide_targets_the_reader_cannot_see(world):
    """Detail, list and queue follow the node:read rule of each target."""
    item = await _item_on_fresh_node(world)
    for target in ("node_team", "node_elders"):
        await _suggest(world, item, target)
    team, elders = str(world.res["node_team"]), str(world.res["node_elders"])

    async def targets(who: str) -> list[set]:
        views = []
        for url in (
            f"/api/parlementair/imports/{item.id}",
            "/api/parlementair/imports",
            "/api/parlementair/review-queue",
        ):
            resp = await request(world, who, "GET", url)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            if isinstance(body, list):
                body = next(x for x in body if x["id"] == str(item.id))
            views.append({e["target_node_id"] for e in body["suggested_edges"]})
        return views

    assert await targets("viewer") == [{team}] * 3
    assert await targets("super_admin") == [{team, elders}] * 3
    viewer = world.person["viewer"]
    await add(world, rp("corpus_node", elders, "betrokken", person=viewer))
    assert (await targets("viewer"))[0] == {team, elders}


async def _owners(w: World, node_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await w.db.scalars(
        select(ResourcePermission.person_id).where(
            ResourcePermission.resource_type == "corpus_node",
            ResourcePermission.resource_id == node_id,
            ResourcePermission.rol == "eigenaar",
        )
    )
    return set(rows)


# (reviewer, item node or None for a fresh node, current eigenaars, named
# eigenaar, expected).  The route and ``parlementair:name_owner`` agree.
OWNER_CASES = [
    # the review names someone else who can read the node
    ("team_editor", "node_team", (), "viewer", 200),
    ("ministry_admin", "node_directie", (), "manager", 200),
    ("manager", "node_directie", (), "role_only", 200),  # a resource role reads
    # someone who cannot read the node would receive node:delete on it
    ("team_editor", "node_team", (), "role_only", 403),
    # naming yourself only when you already edit the node
    ("team_editor", "node_team", (), "team_editor", 200),
    ("ministry_admin", "node_directie", (), "ministry_admin", 403),
    # replacing: an editor holds no node:delete, so hands out no eigenaar
    ("team_editor", None, ("afd_editor",), "viewer", 403),
    # two eigenaars used to crash the review with a 500
    ("manager", None, ("team_editor", "afd_editor"), "viewer", 200),
]  # fmt: skip


@pytest.mark.parametrize(("who", "node", "owners", "named", "expected"), OWNER_CASES)
async def test_review_names_the_eigenaar(pw, who, node, owners, named, expected):
    item = await (make_item(pw, node) if node else _item_on_fresh_node(pw))
    node_id = item.corpus_node_id
    for owner in owners:
        await add(pw, rp("corpus_node", node_id, "eigenaar", person=pw.person[owner]))
    target = pw.person[named].id
    question = ask(
        "parlementair:name_owner", "corpus_node", node_id, target_person_id=target
    )
    assert await evaluate(pw, who, question) == [expected == 200]
    resp = await request(
        pw,
        who,
        "POST",
        f"/api/parlementair/imports/{item.id}/complete",
        {"eigenaar_id": str(target), "tasks": []},
    )
    assert resp.status_code == expected, resp.text
    kept = {pw.person[o].id for o in owners}
    assert await _owners(pw, node_id) == ({target} if expected == 200 else kept)


@pytest.mark.parametrize(("tasks", "expected"), [([], 200), ([{"title": "x"}], 403)])
async def test_review_follow_up_tasks_need_task_create(pw, tasks, expected):
    """A ministry_admin reviews, but creates no tasks: POST /tasks refuses too."""
    item = await make_item(pw, "node_directie")
    body = {"eigenaar_id": "{p_manager}", "tasks": tasks}
    url = f"/api/parlementair/imports/{item.id}/complete"
    resp = await request(pw, "ministry_admin", "POST", url, body)
    assert resp.status_code == expected, resp.text


async def test_complete_review_leaves_other_units_tasks_open(pw):
    """Anyone may link a task to an item; the reviewer closes only their own."""
    item = await make_item(pw, "node_directie")
    review = await ParlementairImportService(pw.db).create_review_task(
        item, affected_nodes=[]
    )
    elders = await pw.db.get(Task, pw.res["task_elders"])
    elders.parlementair_item_id = item.id
    await pw.db.flush()
    body = {"eigenaar_id": "{p_manager}", "tasks": []}
    url = f"/api/parlementair/imports/{item.id}/complete"
    resp = await request(pw, "ministry_admin", "POST", url, body)
    assert resp.status_code == 200, resp.text
    await pw.db.refresh(review)
    await pw.db.refresh(elders)
    assert (review.status, elders.status) == ("done", "open")


@pytest.mark.parametrize("path", ["/approve", "/reject", "/reset", ""])
async def test_suggestion_routes_ask_on_the_suggestion(world, path):
    """403 without review rights, 404 for an unknown one; a refused reset
    keeps the approved edge."""
    item = await _item_on_fresh_node(world)
    suggestion = await _suggest(world, item, "node_team")
    edge_id = None
    if path == "/reset":
        url = f"/api/parlementair/edges/{suggestion.id}/approve"
        edge_id = (await request(world, "manager", "PUT", url)).json()["edge_id"]
    method, body = ("PATCH", {"edge_type_id": "x"}) if not path else ("PUT", None)
    base = "/api/parlementair/edges"
    refused = await request(
        world, "viewer", method, f"{base}/{suggestion.id}{path}", body
    )
    missing = await request(
        world, "manager", method, f"{base}/{uuid.uuid4()}{path}", body
    )
    assert (refused.status_code, missing.status_code) == (403, 404), refused.text
    await world.db.refresh(suggestion)
    if edge_id:
        assert await world.db.get(Edge, uuid.UUID(edge_id)) is not None
    else:
        assert suggestion.status == "pending"


async def test_item_response_drops_a_stored_scope_judgement(world):
    """Items from before the fix carry one scope's judgement in extra_data."""
    item = await make_item(world, "node_team")
    item.extra_data = {
        "categorie": "overig",
        "relevantie_reden": "geheim",
        "actie": "x",
    }
    await world.db.flush()
    resp = await request(world, "viewer", "GET", f"/api/parlementair/imports/{item.id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["extra_data"] == {"categorie": "overig"}


async def test_review_unit_follows_membership(world):
    """Informational and ended placements are no membership, however many."""
    from datetime import date, timedelta

    node = await make_node(world.db, "Dossier", world.org["team"])
    owner = await make_person(world.db, "Eigenaar")
    others = [await make_person(world.db, f"Mede-eigenaar {i}") for i in range(2)]
    for person in (owner, *others):
        await add(world, rp("corpus_node", node.id, "eigenaar", person=person))
    await place(world.db, owner, world.org["team"])
    for other in others:
        await place(world.db, other, world.org["elders"], bron="handmatig")
        ended = await place(world.db, other, world.org["dg"])
        ended.eind_datum = date.today() - timedelta(days=7)
    await world.db.flush()
    service = ParlementairImportService(world.db)
    assert await service._determine_review_unit([node]) == world.org["team"].id
