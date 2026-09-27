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
    for scope in ("node_team", "node_directie", "node_free", "initiatief"):
        key = "sa_" + scope.removeprefix("node_")
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


# (permission, resource key, "@eenheid" for a new one there or None for a new
# one anywhere, who; "!who" expects a refusal)
TABLE = [
    # 1. super_admin and the system roles
    ("node:delete", "node_directie", "super_admin"),
    ("org:read", "elders", "platform_admin"),
    ("node:update", "node_elders", "!platform_admin"),
    ("node:update", "node_free", "!platform_admin"),
    ("opdracht:update", "opdracht_afdeling", "!platform_admin"),
    # 2. a resource role on the resource itself
    ("node:update", "node_directie", "role_only"),
    ("node:delete", "node_directie", "!role_only"),
    ("node:update", "node_afdeling", "!role_only"),
    ("initiatief:update", "initiatief", "role_only"),
    ("opdracht:update", "opdracht_directie", "role_only"),
    ("opdracht:delete", "opdracht_directie", "role_only"),
    ("opdracht:update", "opdracht_afdeling", "!role_only"),
    ("org:manage", "elders", "eenheid_eigenaar"),
    ("org:manage", "dg", "!eenheid_eigenaar"),
    # 3. parent delegation: a lead's sub-records, edges, tasks
    ("lead:update", "lead", "role_only !viewer !rp_viewer !team_editor"),
    ("lead:delete", "lead", "!role_only manager"),
    ("lead_column:update", "lead_column", "role_only"),
    ("lead:read", "lead", "rp_viewer"),
    ("lead:create", "initiatief", "!rp_viewer"),
    # the opdrachtgever writes their own lead only
    ("lead:update", "lead", "opdrachtgever"),
    ("lead:delete", "lead", "!opdrachtgever"),
    ("lead:update", "lead_other", "!opdrachtgever"),
    ("lead:update", "lead_free", "!opdrachtgever"),
    ("lead_update:update", "post", "opdrachtgever !rp_viewer"),
    ("lead_activity:delete", "activity", "opdrachtgever !viewer"),
    ("lead_attachment:delete", "attachment", "role_only !rp_viewer"),
    ("github_link:delete", "github_link", "opdrachtgever !team_editor"),
    ("github_link:create", "lead", "opdrachtgever !rp_viewer"),
    ("edge:update", "edge_team_directie", "team_editor"),
    ("edge:update", "edge_directie_elders", "!team_editor role_only"),
    ("edge:delete", "edge_team_directie", "!team_editor"),
    ("edge:delete", "edge_directie_elders", "manager"),
    ("task:update", "task_on_team_node", "afd_editor team_editor"),
    ("task:update", "task_team", "!role_only"),
    # a child permission asked on its parent
    ("edge:create", "node_team", "team_editor"),
    ("edge:create", "node_directie", "!team_editor"),
    ("task:create", "node_directie", "role_only"),
    ("lead:create", "initiatief", "role_only"),
    ("stakeholder_assessment:create", "initiatief", "afd_editor !team_editor"),
    ("stakeholder_assessment:create", "node_team", "team_editor"),
    ("stakeholder_assessment:create", "node_directie", "!team_editor"),
    # stakeholder assessments: write access on their scope
    ("stakeholder_assessment:update", "sa_team", "team_editor"),
    ("stakeholder_assessment:delete", "sa_team", "afd_editor !viewer"),
    ("stakeholder_assessment:update", "sa_directie", "!team_editor role_only"),
    ("stakeholder_assessment:update", "sa_initiatief", "role_only !team_editor"),
    ("stakeholder_assessment:update", "sa_free", "team_editor"),
    # 4. rights on the eenheid, inherited downward only
    ("node:update", "node_afdeling", "afd_editor !team_editor"),
    ("node:update", "node_team", "afd_editor !viewer"),
    ("node:update", "node_directie", "!afd_editor !team_editor"),
    ("node:read", "node_directie", "team_editor"),
    ("node:read", "node_team", "viewer"),
    ("node:delete", "node_team", "manager"),
    ("task:update", "task_team", "afd_editor !viewer"),
    ("task:delete", "task_team", "team_editor"),
    ("initiatief:update", "initiatief", "afd_editor !team_editor"),
    ("lead:update", "lead", "afd_editor"),
    # a lead without initiatief but with an eenheid follows that eenheid
    ("lead:update", "lead_team", "team_editor afd_editor !viewer"),
    # opdrachten: rights on the client or on the team doing the work
    ("opdracht:update", "opdracht_afdeling", "afd_editor"),
    ("opdracht:update", "opdracht_directie", "!afd_editor !team_editor manager"),
    ("opdracht:update", "opdracht_voor_team", "team_editor !viewer"),
    ("opdracht:read", "opdracht_voor_team", "viewer"),
    ("opdracht:delete", "opdracht_afdeling", "manager !afd_editor"),
    # creating: the eenheid it goes into
    ("task:create", "@team", "afd_editor"),
    ("task:create", "@directie", "!afd_editor"),
    ("node:create", "@afdeling", "!team_editor"),
    ("lead:create", "@team", "team_editor"),
    ("lead:create", "@directie", "!team_editor"),
    ("opdracht:create", "@team", "afd_editor"),
    ("opdracht:create", "@directie", "!afd_editor !team_editor"),
    # eenheden: a manager edits below, org:manage from ministry_admin down
    ("org:update", "team", "manager !team_editor super_admin"),
    ("org:update", "elders", "!manager"),
    ("org:manage", "directie", "org_admin !manager"),
    ("org:manage", "team", "org_admin !team_editor"),
    ("org:manage", "dg", "!org_admin"),
    ("org:manage", "elders", "!org_admin"),
    ("org:update", "tooi_team", "!manager super_admin"),
    ("org:read", "tooi_team", "manager"),
    # 5. tenant-wide fallbacks, only for resources without eenheid
    ("node:update", "node_free", "team_editor !viewer !role_only"),
    ("node:create", None, "team_editor"),
    ("lead:update", "lead_free", "team_editor !viewer !rp_viewer"),
    ("lead:delete", "lead_free", "!team_editor manager"),
    # a new lead living nowhere: system roles only (the route places it)
    ("lead:create", None, "!team_editor !viewer super_admin"),
    ("tag:create", None, "team_editor !viewer !role_only"),
    ("tag:update", "tag", "team_editor !viewer"),
    ("tag:delete", "tag", "!afd_editor manager"),
    ("people:create", None, "team_editor !platform_admin !role_only"),
    ("samenwerkingsverband:update", "swv", "team_editor !viewer"),
    ("samenwerkingsverband:delete", "swv", "manager !team_editor"),
    ("samenwerkingsverband:create", None, "team_editor !role_only"),
    ("opdracht:update", "opdracht_free", "team_editor !viewer"),
    ("opdracht:create", None, "team_editor"),
    # no tenant-wide fallback for tasks
    ("task:create", None, "!team_editor"),
]  # fmt: skip
CASES = [
    (who.lstrip("!"), permission, target, not who.startswith("!"))
    for permission, target, whos in TABLE
    for who in whos.split()
]


@pytest.mark.parametrize("case", CASES, ids=[f"{c[0]}-{c[1]}-{c[2]}" for c in CASES])
async def test_can(cw, case):
    who, permission, target, expected = case
    key, eenheid = (None, target[1:]) if target and target[0] == "@" else (target, None)
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
    await add(world, SharedAccess(
        source_eenheid_id=world.org["directie"].id, access_level=level,
        target_eenheid_id=world.org["team"].id, geldig_van=date.today(),
    ))  # fmt: skip
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
    rows = [Lead(title=f"L{i}", stage="verkennen", initiatief_id=init)
            for i in range(n)]  # fmt: skip
    await add(w, *rows)
    return [lead.id for lead in rows]


async def _edges(w: World, n: int) -> list[uuid.UUID]:
    team, et = w.org["team"], w.res["edge_type"]
    edges = [Edge(from_node_id=w.res["node_team"], edge_type_id=et,
                  to_node_id=(await make_node(w.db, f"Buur {i}", team)).id)
             for i in range(n)]  # fmt: skip
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
