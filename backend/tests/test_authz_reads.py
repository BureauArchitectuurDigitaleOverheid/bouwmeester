"""Who may read what: one visibility rule per resource type.

Uses ``world``/``iw`` from ``tests/authz_world.py``.  A member reads up the
line, a role reads down from where it holds, siblings stay hidden.  ``rw``
adds initiatieven owned higher and elsewhere, a personal one, leads whose
only link to a reader is a lead role, and budgeted opdrachten.  ``cw`` adds
rows readable only through a resource role, a share or an assignment.  For
every person lists, details and ``can(<type>:read)`` must agree.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from bouwmeester.core.authz import can
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.shared_access import SharedAccess
from tests.authz_world import (
    World,
    add,
    assert_can_case,
    can_case_id,
    get_json,
    opdracht,
    perm_ctx,
    rp,
    task,
)
from tests.authz_world import (
    request as send,
)
from tests.factories import client_as, grant_role, make_person, place


@pytest.fixture
async def rw(iw: World) -> World:
    db, org, res = iw.db, iw.org, iw.res
    for key, naam, eenheid in (
        ("dg_member", "DG-lid", "dg"),  # reads up, not down
        ("outsider", "Buitenstaander", "elders"),
        ("lead_contact", "Leadcontact", None),
        ("lead_owner", "Opdrachtgever", None),
    ):
        iw.person[key] = await make_person(db, naam)
        if eenheid:
            await place(db, iw.person[key], org[eenheid])
    for key, owner in (
        ("init_dg", {"eenheid": org["dg"]}),
        ("init_elders", {"eenheid": org["elders"]}),
        ("init_personal", {"person": iw.person["role_only"]}),
    ):
        init = await add(iw, Initiatief(id=uuid.uuid4(), naam=f"{key} {uuid.uuid4()}"))
        await add(iw, rp("initiatief", init.id, "eigenaar", **owner))
        res[key] = init.id
    for key, title, init in (
        ("lead_elders", "Lead elders", "init_elders"),
        ("lead_dg", "Lead DG", "init_dg"),
        ("lead_personal", "Eigen lead", "init_personal"),
    ):
        lead = Lead(title=title, stage="verkennen", initiatief_id=res[init])
        res[key] = (await add(iw, lead)).id
    kw = {"status": "actief", "begrotingsjaar": 2025, "instrument_id": res["node_team"]}
    rows = {
        "opdracht_team": opdracht(iw, "Zichtbaar", "team", budget=Decimal(100_000),
                                  gerealiseerd=Decimal(25_000), **kw),
        "opdracht_elders": opdracht(iw, "Onzichtbaar", "elders", **kw,
                                    budget=Decimal(200_000),
                                    gerealiseerd=Decimal(50_000)),
        # client elsewhere, visible to the team only as opdrachtnemer
        "opdracht_voor_team": opdracht(iw, "Voor team", "elders",
                                       opdrachtnemer_eenheid_id=org["team"].id),
        "task_sibling_node": task(iw, "Losse taak", "node_sibling"),
    }  # fmt: skip
    await add(iw, *rows.values())
    res.update({k: v.id for k, v in rows.items()})
    p = iw.person
    await add(
        iw,
        rp("lead", res["lead_dg"], "opdrachtgever", person=p["outsider"]),
        rp("lead", res["lead"], "opdrachtgever", person=p["lead_owner"]),
        rp("lead", res["lead_elders"], "contactpersoon", person=p["lead_contact"]),
        rp("lead", res["lead_personal"], "betrokken", eenheid=org["team"]),
    )
    return iw


@pytest.fixture
async def cw(world: World) -> World:
    """Rows that lists, details and decisions used to disagree on."""
    db, res, viewer = world.db, world.res, world.person["viewer"]
    editor = world.person["elders_editor"] = await make_person(db, "Redacteur elders")
    await place(db, editor, world.org["elders"])
    await grant_role(db, editor, "editor", world.org["elders"])
    rows = {
        "opdracht_elders": opdracht(world, "Opdracht elders", "elders"),
        "task_on_elders_node": task(world, "Losse taak elders", "node_elders"),
        "task_assigned": task(
            world, "Toegewezen", "node_elders", "elders", assignee_id=viewer.id
        ),
        "lead_elders": Lead(title="Lead elders", stage="verkennen",
                            organisatie_eenheid_id=world.org["elders"].id),
    }  # fmt: skip
    await add(world, *rows.values())
    res.update({k: v.id for k, v in rows.items()})
    await add(
        world,
        rp("corpus_node", res["node_elders"], "adviseur", person=viewer),
        rp("opdracht", res["opdracht_elders"], "betrokken", person=viewer),
        # role_only holds no role anywhere, so no opdrachten module
        rp("opdracht", res["opdracht_elders"], "eigenaar",
           person=world.person["role_only"]),
        SharedAccess(source_node_id=res["node_sibling"], access_level="edit",
                     target_eenheid_id=world.org["team"].id,
                     geldig_van=date.today() - timedelta(days=1)),
    )  # fmt: skip
    return world


# ---------------------------------------------------------------------------
# Lists, details and can(read) agree, for everyone on everything
# ---------------------------------------------------------------------------

# (type, read permission, list route or None, detail route, key prefixes)
SURFACES = [
    ("corpus_node", "node:read", "/api/nodes?limit=500", "/api/nodes/{}", ("node_",)),
    ("task", "task:read", "/api/tasks?limit=500", "/api/tasks/{}", ("task_",)),
    ("edge", "edge:read", "/api/edges?limit=500", "/api/edges/{}", ("edge_",)),
    ("opdracht", "opdracht:read", "/api/opdrachten", "/api/opdrachten/{}",
     ("opdracht_",)),
    ("initiatief", "initiatief:read", "/api/initiatieven?limit=500",
     "/api/initiatieven/{}", ("initiatief", "init_")),
    ("lead", "lead:read", "/api/leads?limit=500", "/api/leads/{}", ("lead",)),
]  # fmt: skip
_NOT_A_ROW = {"lead_column", "edge_type"}


def _keys(w: World, prefixes: tuple[str, ...]) -> list[str]:
    return [k for k in w.res if k.startswith(prefixes) and k not in _NOT_A_ROW]


async def _disagreements(w: World, surface) -> list:
    resource_type, permission, list_path, detail, prefixes = surface
    keys = _keys(w, prefixes)
    mismatches = []
    for who, person in w.person.items():
        ctx = await perm_ctx(w, who)
        async with client_as(w.db, person) as c:
            resp = await c.get(list_path)
            ok = resp.status_code == 200
            listed = {i["id"] for i in resp.json()} if ok else set()
            for key in keys:
                rid = w.res[key]
                row = {
                    str(rid) in listed,
                    (await c.get(detail.format(rid))).status_code == 200,
                    await can(w.db, ctx, permission, resource_type, rid),
                }
                if resource_type == "lead":
                    channels = await c.get(f"/api/leads/{rid}/mattermost-channels")
                    row.add(channels.status_code == 200)
                if len(row) != 1:
                    mismatches.append((who, key))
    return mismatches


async def _write_without_read(w: World) -> list:
    offenders = []
    for who in w.person:
        ctx = await perm_ctx(w, who)
        for resource_type, _, _, _, prefixes in SURFACES:
            domain = {"corpus_node": "node"}.get(resource_type, resource_type)
            for key in _keys(w, prefixes):
                rid = w.res[key]
                if not await can(w.db, ctx, f"{domain}:update", resource_type, rid):
                    continue
                if not await can(w.db, ctx, f"{domain}:read", resource_type, rid):
                    offenders.append((who, key))
    return offenders


_IDS = [s[0] for s in SURFACES]


@pytest.mark.parametrize("surface", SURFACES, ids=_IDS)
async def test_list_detail_and_can_read_agree_in_the_tree(rw, surface):
    assert not await _disagreements(rw, surface)


@pytest.mark.parametrize("surface", SURFACES, ids=_IDS)
async def test_list_detail_and_can_read_agree_on_roles_and_shares(cw, surface):
    assert not await _disagreements(cw, surface)


async def test_whoever_may_write_may_read_in_the_tree(rw):
    assert not await _write_without_read(rw)


async def test_whoever_may_write_may_read_on_roles_and_shares(cw):
    assert not await _write_without_read(cw)


async def test_sub_records_read_through_their_parent(rw):
    for who in rw.person:
        ctx = await perm_ctx(rw, who)
        column = await can(
            rw.db, ctx, "lead_column:read", "lead_column", rw.res["lead_column"]
        )
        parent = await can(rw.db, ctx, "initiatief:read", "initiatief",
                           rw.res["initiatief"])  # fmt: skip
        assert column is parent, who


# ---------------------------------------------------------------------------
# The org chart: up the line, down from a role, never sideways
# ---------------------------------------------------------------------------

# (who, list route, resource key, listed?)
LISTS = [
    ("viewer", "/api/nodes?limit=500", "node_team", True),
    ("viewer", "/api/nodes?limit=500", "node_free", True),  # no eenheid: everyone
    ("viewer", "/api/nodes?limit=500", "node_elders", False),
    ("afd_editor", "/api/nodes?search=Teamdossier", "node_team", True),  # below
    ("viewer", "/api/tasks?limit=500", "task_team", True),
    ("viewer", "/api/tasks?limit=500", "task_elders", False),
    ("viewer", "/api/tasks?node_id={node_elders}", "task_elders", False),
    ("viewer", "/api/tasks?limit=500", "task_sibling_node", False),  # via its node
    ("afd_editor", "/api/tasks?limit=500", "task_sibling_node", True),
    ("viewer", "/api/edges?limit=500", "edge_team_directie", True),
    ("viewer", "/api/edges?limit=500", "edge_directie_elders", False),  # one end hidden
    ("viewer", "/api/opdrachten", "opdracht_team", True),
    ("viewer", "/api/opdrachten", "opdracht_free", True),  # no eenheid: everyone
    ("viewer", "/api/opdrachten", "opdracht_elders", False),
    ("viewer", "/api/opdrachten", "opdracht_voor_team", True),  # as opdrachtnemer
    ("viewer", "/api/nodes/{node_team}/opdrachten", "opdracht_team", True),
    ("viewer", "/api/nodes/{node_team}/opdrachten", "opdracht_elders", False),
]  # fmt: skip


@pytest.mark.parametrize(("who", "path", "key", "listed"), LISTS)
async def test_lists_follow_the_org_chart(rw, who, path, key, listed):
    body = await get_json(rw, who, path)
    assert (str(rw.res[key]) in {i["id"] for i in body}) is listed


_MISSING = "00000000-0000-4000-8000-000000000000"
_SA = "/api/stakeholder-assessments?scope_type="
_OVERVIEW = "/api/tasks/eenheid-overview?organisatie_eenheid_id="

# (who, detail route, status): a hidden record is a 404, like a missing one
DETAILS = [
    ("viewer", "/api/nodes/{node_team}", 200),
    ("viewer", "/api/nodes/{node_elders}", 404),
    ("viewer", "/api/nodes/{node_sibling}", 404),  # the team next door
    ("team_editor", "/api/nodes/{node_sibling}", 404),
    ("afd_editor", "/api/nodes/{node_team}", 200),  # rights inherit downward
    ("viewer", "/api/tasks/{task_elders}", 404),
    ("viewer", "/api/tasks/{task_sibling_node}", 404),
    ("afd_editor", "/api/tasks/{task_sibling_node}", 200),
    ("viewer", "/api/tasks/{task_elders}/subtasks", 404),
    ("viewer", _OVERVIEW + "{eenheid_elders}", 404),
    ("viewer", "/api/edges/{edge_directie_elders}", 404),
    ("viewer", "/api/opdrachten/{opdracht_team}", 200),
    ("viewer", "/api/opdrachten/{opdracht_elders}", 404),
    ("viewer", "/api/nodes/{node_elders}/opdrachten", 404),
    ("viewer", "/api/nodes/{node_elders}/financieel", 404),
    # a ministry_admin reads down into the tree below its directie only
    ("org_admin", "/api/nodes/{node_team}", 200),
    ("org_admin", "/api/nodes/{node_elders}", 404),
    # stakeholder assessments are read where their scope is visible
    ("viewer", _SA + "corpus_node&scope_id={node_team}", 200),
    ("viewer", _SA + "corpus_node&scope_id={node_sibling}", 404),
    ("viewer", _SA + "corpus_node&scope_id=" + _MISSING, 404),
    ("viewer", _SA + "initiatief&scope_id={initiatief}", 200),
    ("viewer", "/api/initiatieven/{init_dg}", 200),  # a member reads up
]  # fmt: skip


@pytest.mark.parametrize(("who", "path", "expected"), DETAILS)
async def test_details_follow_the_org_chart(rw, who, path, expected):
    resp = await send(rw, who, "GET", path)
    assert resp.status_code == expected, resp.text


async def test_summary_counts_only_visible_opdrachten(rw):
    summary = await get_json(rw, "viewer", "/api/opdrachten/summary")
    # opdracht_team, plus opdracht_free, _directie and _voor_team without budget
    assert int(summary["count"]) == 4
    assert Decimal(str(summary["totaal_budget"])) == Decimal(100_000)
    assert Decimal(str(summary["totaal_gerealiseerd"])) == Decimal(25_000)


# ---------------------------------------------------------------------------
# Initiatieven and leads
# ---------------------------------------------------------------------------

INITIATIEVEN = ("initiatief", "init_dg", "init_elders", "init_personal")
LEADS = ("lead", "lead_free", "lead_elders", "lead_dg", "lead_personal")

# (list route, who, what they see); owners: afdeling, DG, elders, role_only
SEES = [
    ("/api/initiatieven", "super_admin", INITIATIEVEN),
    ("/api/initiatieven", "manager", ("initiatief", "init_dg")),  # directie below DG
    ("/api/initiatieven", "afd_editor", ("initiatief", "init_dg")),  # and up the line
    ("/api/initiatieven", "viewer", ("initiatief", "init_dg")),
    ("/api/initiatieven", "team_editor", ("initiatief", "init_dg")),
    ("/api/initiatieven", "role_only", ("initiatief", "init_personal")),
    ("/api/initiatieven", "dg_member", ("init_dg",)),  # does not read down
    ("/api/initiatieven", "outsider", ("init_dg", "init_elders")),
    ("/api/initiatieven", "partner_member", INITIATIEVEN[:3]),
    ("/api/initiatieven", "platform_admin", ()),
    # lead_free has no initiatief: every logged-in user sees it
    ("/api/leads", "outsider", ("lead_free", "lead_elders", "lead_dg")),
    ("/api/leads", "lead_contact", ("lead_free", "lead_elders")),  # contact only
    ("/api/leads", "dg_member", ("lead_free", "lead_dg")),
    # the team holds a role on the personal initiatief's lead
    ("/api/leads", "viewer", ("lead", "lead_free", "lead_dg", "lead_personal")),
    # writes the afdeling's lead without seeing its initiatief
    ("/api/leads", "lead_owner", ("lead", "lead_free")),
]  # fmt: skip


@pytest.mark.parametrize(
    ("path", "who", "sees"), SEES, ids=[f"{s[0]}-{s[1]}" for s in SEES]
)
async def test_who_sees_which_initiatief_and_lead(rw, path, who, sees):
    universe = {str(rw.res[k]) for k in INITIATIEVEN + LEADS}
    listed = {i["id"] for i in await get_json(rw, who, path, limit=500)} & universe
    assert listed == {str(rw.res[k]) for k in sees}
    if path == "/api/leads":  # search applies the same rule
        found = await get_json(rw, who, "/api/search", q="Lead", result_types="lead")
        assert {r["id"] for r in found["results"]} & universe == listed  # fmt: skip


async def test_by_eenheid_lists_only_visible_initiatieven(rw):
    path = "/api/initiatieven/by-eenheid/{eenheid_afdeling}"
    assert await get_json(rw, "dg_member", path) == []
    shown = await get_json(rw, "team_editor", path)
    assert [i["initiatief_id"] for i in shown] == [str(rw.res["initiatief"])]


# ---------------------------------------------------------------------------
# Resource roles, shares and assignments make things readable
# ---------------------------------------------------------------------------

ROLE_AND_SHARE_READS = [
    ("viewer", "node:read", "corpus_node", "node_elders", None, True),  # adviseur
    ("viewer", "opdracht:read", "opdracht", "opdracht_elders", None, True),  # betrokken
    ("viewer", "task:read", "task", "task_on_elders_node", None, True),  # its node
    ("viewer", "task:read", "task", "task_assigned", None, True),  # own task
    ("viewer", "task:read", "task", "task_elders", None, False),
    ("viewer", "node:read", "corpus_node", "node_sibling", None, True),  # shared
    ("team_editor", "node:update", "corpus_node", "node_sibling", None, True),
    ("viewer", "lead:read", "lead", "lead_elders", None, False),  # eenheid hidden
    ("elders_editor", "lead:read", "lead", "lead_elders", None, True),
    ("viewer", "lead:read", "lead", "lead_free", None, True),  # no place at all
    ("role_only", "node:read", "corpus_node", "node_directie", None, True),
    ("role_only", "node:update", "corpus_node", "node_directie", None, True),
    # without the opdrachten module only a role on the opdracht itself counts
    ("role_only", "opdracht:update", "opdracht", "opdracht_elders", None, True),
    ("role_only", "opdracht:read", "opdracht", "opdracht_elders", None, True),
    ("role_only", "opdracht:read", "opdracht", "opdracht_free", None, False),
]  # fmt: skip


@pytest.mark.parametrize(
    "case", ROLE_AND_SHARE_READS, ids=[can_case_id(c) for c in ROLE_AND_SHARE_READS]
)
async def test_roles_and_shares_make_things_readable(cw, case):
    await assert_can_case(cw, case)


# (who, query, result type, key, found?)
SEARCH = [
    ("elders_editor", "zonder eenheid", "task", "task_on_team_node", False),
    ("team_editor", "zonder eenheid", "task", "task_on_team_node", True),
    ("viewer", "Dossier", "corpus_node", "node_elders", True),  # adviseur
    ("viewer", "Dossier", "corpus_node", "node_sibling", True),  # shared
    ("viewer", "Dossier", "corpus_node", "node_free", True),
    ("elders_editor", "Teamdossier", "corpus_node", "node_team", False),
    ("viewer", "Lead elders", "lead", "lead_elders", False),
    ("elders_editor", "Lead elders", "lead", "lead_elders", True),
]  # fmt: skip


@pytest.mark.parametrize(("who", "q", "result_type", "key", "found"), SEARCH)
async def test_search_applies_the_read_rules(cw, who, q, result_type, key, found):
    body = await get_json(cw, who, "/api/search", q=q, result_types=result_type)
    assert (str(cw.res[key]) in {r["id"] for r in body["results"]}) is found


async def test_assignee_without_role_reads_only_own_task(world):
    freelancer = await make_person(world.db, "Zonder rol")
    world.person["freelancer"] = freelancer
    own = task(world, "Voor hem", "node_team", "team", assignee_id=freelancer.id)
    await add(world, own)
    ctx = await perm_ctx(world, "freelancer")
    assert await can(world.db, ctx, "task:read", "task", own.id)
    assert not await can(world.db, ctx, "task:update", "task", own.id)
    other = await send(world, "freelancer", "GET", "/api/tasks/{task_team}")
    assert other.status_code == 404, other.text
    assert (await send(world, "freelancer", "GET", f"/api/tasks/{own.id}")).is_success
    for params in ({"assignee_id": str(freelancer.id)}, {}):
        listed = await get_json(world, "freelancer", "/api/tasks", **params)
        assert [t["id"] for t in listed] == [str(own.id)]
