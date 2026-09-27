"""The single decision point ``can()`` (``core/authz.py``), step by step.

On ``iw`` from ``tests/authz_world.py`` plus ``cw``: an opdrachtgever of the
lead, a lead of the team, sub-records of the lead, opdrachten, a tag,
stakeholder assessments and an eigenaar of the eenheid ``elders``.  One
table covers every resolution step; the query-count tests guard the
deliberate promise that deciding many things costs a constant number of
queries.
"""

import uuid
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from bouwmeester.core.authz import can, prefetch, require
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.edge import Edge
from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.models.tag import Tag
from tests.authz_world import (
    World,
    add,
    ask,
    assert_can_case,
    make_node,
    opdracht,
    perm_ctx,
    rights_level,
    rp,
)
from tests.factories import client_as, make_org, make_person


@pytest.fixture
async def cw(iw: World) -> World:
    w, lead, team, db = iw, iw.res["lead"], iw.org["team"], iw.db
    opdrachtgever = await make_person(db, "Opdrachtgever")
    eigenaar = await make_person(db, "Aanmaker stakeholder-eenheid")
    w.person.update(opdrachtgever=opdrachtgever, eenheid_eigenaar=eigenaar)
    w.org["tooi_team"] = await make_org(db, "TOOI-team", "team", w.org["directie"])
    w.org["tooi_team"].bron = "tooi"  # synced: read-only below super_admin
    role_only, init = w.person["role_only"], w.res["initiatief"]
    rows = {
        "lead_other": Lead(title="L", stage="verkennen", initiatief_id=init),
        "lead_team": Lead(title="T", stage="verkennen", organisatie_eenheid_id=team.id),
        "activity": LeadActivity(lead_id=lead, content="N", activity_type="note",
                                 author_id=role_only.id),
        "post": LeadUpdatePost(lead_id=lead, titel="Update"),
        "attachment": LeadAttachment(lead_id=lead, soort="link", url="https://x.nl"),
        "github_link": GitHubLink(scope_type=SCOPE_LEAD, scope_id=lead, owner="foo",
                                  url="https://github.com/foo/bar/pull/1", repo="bar",
                                  link_type="pull_request"),
        "opdracht_afdeling": opdracht(w, "Afdeling", "afdeling"),
        # client elsewhere, the team does the work: the team answers for it too
        "opdracht_voor_team": opdracht(w, "T", "elders",
                                       opdrachtnemer_eenheid_id=team.id),
        "tag": Tag(name=f"authz-{uuid.uuid4().hex[:8]}"),
    }  # fmt: skip
    for key, scope in (
        ("sa_team", "node_team"),
        ("sa_directie", "node_directie"),
        ("sa_free", "node_free"),
        ("sa_initiatief", "initiatief"),
    ):
        rows[key] = StakeholderAssessment(
            person_id=w.person["viewer"].id, scope_id=w.res[scope], belang=3,
            scope_type="initiatief" if scope == "initiatief" else "corpus_node",
        )  # fmt: skip
    await add(
        w,
        *rows.values(),
        rp("lead", lead, "opdrachtgever", person=opdrachtgever),
        rp("opdracht", w.res["opdracht_directie"], "eigenaar", person=role_only),
        rp("organisatie_eenheid", w.org["elders"].id, "eigenaar", person=eigenaar),
    )  # fmt: skip
    w.res.update({k: v.id for k, v in rows.items()}, swv=w.res["samenwerkingsverband"])
    return w


_KEY_TYPES = {
    "node": "corpus_node", "edge": "edge", "task": "task", "lead": "lead",
    "initiatief": "initiatief", "opdracht": "opdracht", "tag": "tag",
    "sa": "stakeholder_assessment", "swv": "samenwerkingsverband",
    "post": "lead_update", "activity": "lead_activity",
    "attachment": "lead_attachment", "github": "github_link",
}  # fmt: skip
_PERMISSION_TYPES = {"node": "corpus_node", "people": "person"}


def _resource_type(w: World, permission: str, key: str | None) -> str:
    """The type asked about: of the resource, or of the permission for a new one."""
    if key is None:
        domain = permission.split(":")[0]
        return _PERMISSION_TYPES.get(domain, domain)
    if key in w.org:
        return "organisatie_eenheid"
    if key == "lead_column":
        return key
    return _KEY_TYPES[key.split("_")[0]]


# (who, permission, resource key or None, eenheid key for a new one, expected)
CASES = [
    # 1. super_admin and the system roles
    ("super_admin", "node:delete", "node_directie", None, True),
    ("platform_admin", "org:read", "elders", None, True),
    ("platform_admin", "node:update", "node_elders", None, False),
    ("platform_admin", "node:update", "node_free", None, False),
    ("platform_admin", "opdracht:update", "opdracht_afdeling", None, False),
    # 2. a resource role on the resource itself
    ("role_only", "node:update", "node_directie", None, True),
    ("role_only", "node:delete", "node_directie", None, False),
    ("role_only", "node:update", "node_afdeling", None, False),
    ("role_only", "initiatief:update", "initiatief", None, True),
    ("role_only", "opdracht:update", "opdracht_directie", None, True),
    ("role_only", "opdracht:delete", "opdracht_directie", None, True),
    ("role_only", "opdracht:update", "opdracht_afdeling", None, False),
    ("eenheid_eigenaar", "org:manage", "elders", None, True),
    ("eenheid_eigenaar", "org:manage", "dg", None, False),
    # 3. parent delegation: a lead's sub-records, edges, tasks
    ("role_only", "lead:update", "lead", None, True),  # contributor
    ("role_only", "lead:delete", "lead", None, False),
    ("role_only", "lead_column:update", "lead_column", None, True),
    ("viewer", "lead:update", "lead", None, False),
    ("rp_viewer", "lead:read", "lead", None, True),
    ("rp_viewer", "lead:update", "lead", None, False),
    ("rp_viewer", "lead:create", "initiatief", None, False),
    ("manager", "lead:delete", "lead", None, True),  # initiatief:delete
    ("team_editor", "lead:update", "lead", None, False),
    # the opdrachtgever writes their own lead only
    ("opdrachtgever", "lead:update", "lead", None, True),
    ("opdrachtgever", "lead:delete", "lead", None, False),
    ("opdrachtgever", "lead:update", "lead_other", None, False),
    ("opdrachtgever", "lead:update", "lead_free", None, False),
    ("opdrachtgever", "lead_update:update", "post", None, True),
    ("rp_viewer", "lead_update:update", "post", None, False),
    ("opdrachtgever", "lead_activity:delete", "activity", None, True),
    ("viewer", "lead_activity:delete", "activity", None, False),
    ("role_only", "lead_attachment:delete", "attachment", None, True),
    ("rp_viewer", "lead_attachment:delete", "attachment", None, False),
    ("opdrachtgever", "github_link:delete", "github_link", None, True),
    ("team_editor", "github_link:delete", "github_link", None, False),
    ("opdrachtgever", "github_link:create", "lead", None, True),
    ("rp_viewer", "github_link:create", "lead", None, False),
    ("team_editor", "edge:update", "edge_team_directie", None, True),
    ("team_editor", "edge:update", "edge_directie_elders", None, False),
    ("team_editor", "edge:delete", "edge_team_directie", None, False),
    ("manager", "edge:delete", "edge_directie_elders", None, True),
    ("role_only", "edge:update", "edge_directie_elders", None, True),
    ("afd_editor", "task:update", "task_on_team_node", None, True),
    ("team_editor", "task:update", "task_on_team_node", None, True),
    ("role_only", "task:update", "task_team", None, False),  # the team's task
    # a child permission asked on its parent
    ("team_editor", "edge:create", "node_team", None, True),
    ("team_editor", "edge:create", "node_directie", None, False),
    ("role_only", "task:create", "node_directie", None, True),
    ("role_only", "lead:create", "initiatief", None, True),
    ("afd_editor", "stakeholder_assessment:create", "initiatief", None, True),
    ("team_editor", "stakeholder_assessment:create", "initiatief", None, False),
    ("team_editor", "stakeholder_assessment:create", "node_team", None, True),
    ("team_editor", "stakeholder_assessment:create", "node_directie", None, False),
    # stakeholder assessments: write access on their scope
    ("team_editor", "stakeholder_assessment:update", "sa_team", None, True),
    ("afd_editor", "stakeholder_assessment:delete", "sa_team", None, True),
    ("team_editor", "stakeholder_assessment:update", "sa_directie", None, False),
    ("viewer", "stakeholder_assessment:delete", "sa_team", None, False),
    ("role_only", "stakeholder_assessment:update", "sa_directie", None, True),
    ("role_only", "stakeholder_assessment:update", "sa_initiatief", None, True),
    ("team_editor", "stakeholder_assessment:update", "sa_initiatief", None, False),
    ("team_editor", "stakeholder_assessment:update", "sa_free", None, True),
    # 4. rights on the eenheid, inherited downward only
    ("afd_editor", "node:update", "node_afdeling", None, True),
    ("afd_editor", "node:update", "node_team", None, True),
    ("afd_editor", "node:update", "node_directie", None, False),
    ("team_editor", "node:update", "node_directie", None, False),
    ("team_editor", "node:read", "node_directie", None, True),  # seen above
    ("team_editor", "node:update", "node_afdeling", None, False),
    ("viewer", "node:update", "node_team", None, False),
    ("viewer", "node:read", "node_team", None, True),
    ("manager", "node:delete", "node_team", None, True),
    ("afd_editor", "task:update", "task_team", None, True),
    ("team_editor", "task:delete", "task_team", None, True),
    ("viewer", "task:update", "task_team", None, False),
    ("afd_editor", "initiatief:update", "initiatief", None, True),
    ("team_editor", "initiatief:update", "initiatief", None, False),
    ("afd_editor", "lead:update", "lead", None, True),
    # a lead without initiatief but with an eenheid follows that eenheid
    ("team_editor", "lead:update", "lead_team", None, True),
    ("afd_editor", "lead:update", "lead_team", None, True),
    ("viewer", "lead:update", "lead_team", None, False),
    # opdrachten: rights on the client or on the team doing the work
    ("afd_editor", "opdracht:update", "opdracht_afdeling", None, True),
    ("afd_editor", "opdracht:update", "opdracht_directie", None, False),
    ("team_editor", "opdracht:update", "opdracht_voor_team", None, True),
    ("viewer", "opdracht:update", "opdracht_voor_team", None, False),
    ("viewer", "opdracht:read", "opdracht_voor_team", None, True),
    ("manager", "opdracht:delete", "opdracht_afdeling", None, True),
    ("afd_editor", "opdracht:delete", "opdracht_afdeling", None, False),
    ("team_editor", "opdracht:update", "opdracht_directie", None, False),
    ("manager", "opdracht:update", "opdracht_directie", None, True),
    # creating: the eenheid it goes into
    ("afd_editor", "task:create", None, "team", True),
    ("afd_editor", "task:create", None, "directie", False),
    ("team_editor", "node:create", None, "afdeling", False),
    ("team_editor", "lead:create", None, "team", True),
    ("team_editor", "lead:create", None, "directie", False),
    ("afd_editor", "opdracht:create", None, "team", True),
    ("afd_editor", "opdracht:create", None, "directie", False),
    ("team_editor", "opdracht:create", None, "directie", False),
    # eenheden: a manager edits below, org:manage from ministry_admin down
    ("manager", "org:update", "team", None, True),
    ("manager", "org:update", "elders", None, False),
    ("team_editor", "org:update", "team", None, False),
    ("super_admin", "org:update", "team", None, True),
    ("org_admin", "org:manage", "directie", None, True),
    ("org_admin", "org:manage", "team", None, True),
    ("org_admin", "org:manage", "dg", None, False),
    ("org_admin", "org:manage", "elders", None, False),
    ("team_editor", "org:manage", "team", None, False),
    ("manager", "org:manage", "directie", None, False),
    ("manager", "org:update", "tooi_team", None, False),  # synced: read-only
    ("manager", "org:read", "tooi_team", None, True),
    ("super_admin", "org:update", "tooi_team", None, True),
    # 5. tenant-wide fallbacks, only for resources without eenheid
    ("team_editor", "node:update", "node_free", None, True),
    ("team_editor", "node:create", None, None, True),
    ("viewer", "node:update", "node_free", None, False),
    ("role_only", "node:update", "node_free", None, False),
    ("team_editor", "lead:update", "lead_free", None, True),
    ("viewer", "lead:update", "lead_free", None, False),
    ("rp_viewer", "lead:update", "lead_free", None, False),
    ("team_editor", "lead:delete", "lead_free", None, False),
    ("manager", "lead:delete", "lead_free", None, True),
    # a new lead living nowhere: system roles only (the route places it)
    ("team_editor", "lead:create", None, None, False),
    ("viewer", "lead:create", None, None, False),
    ("super_admin", "lead:create", None, None, True),
    ("team_editor", "tag:create", None, None, True),
    ("viewer", "tag:create", None, None, False),
    ("role_only", "tag:create", None, None, False),
    ("team_editor", "tag:update", "tag", None, True),
    ("afd_editor", "tag:delete", "tag", None, False),
    ("manager", "tag:delete", "tag", None, True),
    ("viewer", "tag:update", "tag", None, False),
    ("team_editor", "people:create", None, None, True),
    ("platform_admin", "people:create", None, None, False),
    ("role_only", "people:create", None, None, False),
    ("team_editor", "samenwerkingsverband:update", "swv", None, True),
    ("viewer", "samenwerkingsverband:update", "swv", None, False),
    ("manager", "samenwerkingsverband:delete", "swv", None, True),
    ("team_editor", "samenwerkingsverband:delete", "swv", None, False),
    ("team_editor", "samenwerkingsverband:create", None, None, True),
    ("role_only", "samenwerkingsverband:create", None, None, False),
    ("team_editor", "opdracht:update", "opdracht_free", None, True),
    ("viewer", "opdracht:update", "opdracht_free", None, False),
    ("team_editor", "opdracht:create", None, None, True),
    # no tenant-wide fallback for tasks
    ("team_editor", "task:create", None, None, False),
]  # fmt: skip


@pytest.mark.parametrize(
    "case", CASES, ids=[f"{c[0]}-{c[1]}-{c[2] or c[3] or 'new'}" for c in CASES]
)
async def test_can(cw, case):
    who, permission, key, eenheid, expected = case
    resource_type = _resource_type(cw, permission, key)
    await assert_can_case(cw, (who, permission, resource_type, key, eenheid, expected))


LEVELS = {
    "super_admin": "eigenaar",
    "manager": "eigenaar",  # unit_manager on the directie above
    "afd_editor": "eigenaar",  # member of the owning afdeling
    "role_only": "contributor",  # direct resource role
    "partner_member": "contributor",  # via the eenheid's resource role
    "rp_viewer": "viewer",
    # initiatief:update below the owner does not count; reading up does
    "team_editor": "viewer",
    "viewer": "viewer",
    "platform_admin": None,
}


@pytest.mark.parametrize("who", LEVELS)
async def test_initiatief_rights_count_only_where_they_hold(iw, who):
    ctx = await perm_ctx(iw, who)
    assert await rights_level(iw.db, ctx, iw.res["initiatief"]) == LEVELS[who]


async def test_require_raises_404_403_401(world):
    db, node = world.db, world.res
    ctx = await perm_ctx(world, "team_editor")
    for rid, status in ((uuid.uuid4(), 404), (node["node_directie"], 403)):
        with pytest.raises(HTTPException) as refused:
            await require(db, ctx, "node:update", "corpus_node", rid)
        assert refused.value.status_code == status
    await require(db, ctx, "node:update", "corpus_node", node["node_team"])
    anonymous = PermissionContext(is_authenticated=False)
    with pytest.raises(HTTPException) as anon:
        await require(db, anonymous, "node:read", "corpus_node", node["node_free"])
    assert anon.value.status_code == 401
    assert not await can(db, anonymous, "node:read", "corpus_node", node["node_free"])
    # a missing resource is no, even for super_admin
    admin = await perm_ctx(world, "super_admin")
    assert not await can(db, admin, "edge:update", "edge", uuid.uuid4())


@pytest.mark.parametrize(("level", "expected"), [("edit", True), ("read", False)])
async def test_edit_share_grants_write_with_own_rights(world, level, expected):
    """An edit share of the directie to the team lets team editors write there."""
    await add(
        world,
        SharedAccess(
            source_eenheid_id=world.org["directie"].id,
            target_eenheid_id=world.org["team"].id,
            access_level=level,
            geldig_van=date.today(),
        ),
    )
    node = world.res["node_directie"]
    for who, may in (("team_editor", expected), ("viewer", False)):
        ctx = await perm_ctx(world, who)
        assert await can(world.db, ctx, "node:update", "corpus_node", node) is may


# ---------------------------------------------------------------------------
# Query counts: many decisions cost the same as a few
# ---------------------------------------------------------------------------


@contextmanager
def _counting(db):
    """Counts the ORM statements run inside the block."""
    count = [0]

    def _count(*_args):
        count[0] += 1

    event.listen(db.sync_session, "do_orm_execute", _count)
    try:
        yield count
    finally:
        event.remove(db.sync_session, "do_orm_execute", _count)


async def _evaluation_queries(w: World, who: str, asks: list, expected: bool) -> int:
    async with client_as(w.db, w.person[who]) as c:
        with _counting(w.db) as count:
            resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
    assert resp.status_code == 200, resp.text
    assert {d["decision"] for d in resp.json()["evaluations"]} == {expected}
    return count[0]


async def _leads(w: World, n: int) -> list[uuid.UUID]:
    init = w.res["initiatief"]
    rows = [
        Lead(title=f"L{i}", stage="verkennen", initiatief_id=init) for i in range(n)
    ]
    await add(w, *rows)
    return [lead.id for lead in rows]


async def _edges(w: World, n: int) -> list[uuid.UUID]:
    edges = [
        Edge(
            from_node_id=w.res["node_team"],
            to_node_id=(await make_node(w.db, f"Buur {i}", w.org["team"])).id,
            edge_type_id=w.res["edge_type"],
        )
        for i in range(n)
    ]
    await add(w, *edges)
    return [edge.id for edge in edges]


async def _nodes_elders(w: World, n: int) -> list[uuid.UUID]:
    return [(await make_node(w.db, f"E{i}", w.org["elders"])).id for i in range(n)]


# (who, action, resource type, maker, decision): a board, a node page, and a
# refusal that walks every step (edit shares, placements) once per request
COSTS = [
    ("role_only", "lead:update", "lead", _leads, True),
    ("afd_editor", "lead:update", "lead", _leads, True),
    ("team_editor", "edge:update", "edge", _edges, True),
    ("team_editor", "node:update", "corpus_node", _nodes_elders, False),
]


@pytest.mark.parametrize(
    ("who", "action", "rtype", "make", "expected"),
    COSTS,
    ids=[f"{c[0]}-{c[1]}" for c in COSTS],
)
async def test_evaluation_costs_constant_queries(
    world, who, action, rtype, make, expected
):
    few = [ask(action, rtype, i) for i in await make(world, 5)]
    many = [ask(action, rtype, i) for i in await make(world, 50)]
    assert await _evaluation_queries(
        world, who, many, expected
    ) == await _evaluation_queries(world, who, few, expected)


@pytest.mark.parametrize("who", ["role_only", "afd_editor"])
async def test_prefetch_decides_leads_in_constant_queries(world, who):
    """Owner eenheden and resource roles are looked up once, not per lead."""

    async def decide(n: int) -> int:
        ids = await _leads(world, n)
        ctx = await perm_ctx(world, who)  # fresh: no decisions cached yet
        with _counting(world.db) as count:
            await prefetch(world.db, ctx, "lead", ids)
            for lead in ids:
                assert await can(world.db, ctx, "lead:update", "lead", lead)
        return count[0]

    few = await decide(2)
    assert await decide(12) == few


@pytest.mark.parametrize("count", [3, 30])
async def test_prefetch_loads_chains_in_one_query(world, count):
    """Each node in its own eenheid, each eenheid one level deeper."""
    parent, ids = world.org["afdeling"], []
    for i in range(count):
        parent = await make_org(world.db, f"Laag {i}", "team", parent)
        ids.append((await make_node(world.db, f"Node {i}", parent)).id)
    ctx = await perm_ctx(world, "afd_editor")
    with _counting(world.db) as queries:
        await prefetch(world.db, ctx, "corpus_node", ids)
        after_prefetch = queries[0]
        for node in ids:
            assert await can(world.db, ctx, "node:update", "corpus_node", node)
    assert after_prefetch <= 2  # locations, chains
    assert queries[0] - after_prefetch <= 1  # the edit shares, once
