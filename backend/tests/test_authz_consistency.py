"""One rule per question, wherever it is asked (``core/authz.py``).

On the shared ``world`` (``tests/authz_world.py``), extended with the rows
that used to make lists, details and decisions disagree: a node and an
opdracht read only through a resource role, a node shared with the team, a
task without eenheid on such a node, a task assigned to someone who does
not see its eenheid, and a lead that lives in an eenheid without
initiatief.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import event

from bouwmeester.core import authority
from bouwmeester.core.authz import can, prefetch
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.lead import Lead
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.task import Task
from tests.authz_world import World, ask, perm_ctx
from tests.factories import client_as, grant_role, make_org, make_person, place


@pytest.fixture
async def cw(world: World) -> World:
    db = world.db
    elders_editor = await make_person(db, "Redacteur elders")
    await place(db, elders_editor, world.org["elders"])
    await grant_role(db, elders_editor, "editor", world.org["elders"])
    world.person["elders_editor"] = elders_editor

    viewer = world.person["viewer"]  # placed in the team, no role
    opdracht_elders = Opdracht(
        type="opdracht",
        titel="Opdracht elders",
        begrotingsjaar=2026,
        opdrachtgever_id=world.org["elders"].id,
    )
    task_on_elders_node = Task(
        title="Losse taak elders", node_id=world.res["node_elders"], status="open"
    )
    task_assigned = Task(
        title="Toegewezen taak elders",
        node_id=world.res["node_elders"],
        organisatie_eenheid_id=world.org["elders"].id,
        assignee_id=viewer.id,
        status="open",
    )
    lead_elders = Lead(
        title="Lead elders",
        stage="verkennen",
        organisatie_eenheid_id=world.org["elders"].id,
    )
    db.add_all([opdracht_elders, task_on_elders_node, task_assigned, lead_elders])
    await db.flush()
    db.add_all(
        [
            # the viewer reads node_elders and opdracht_elders through a role
            ResourcePermission(
                person_id=viewer.id,
                resource_type="corpus_node",
                resource_id=world.res["node_elders"],
                rol="adviseur",
            ),
            ResourcePermission(
                person_id=viewer.id,
                resource_type="opdracht",
                resource_id=opdracht_elders.id,
                rol="betrokken",
            ),
            # role_only holds no role anywhere, so no opdrachten module
            ResourcePermission(
                person_id=world.person["role_only"].id,
                resource_type="opdracht",
                resource_id=opdracht_elders.id,
                rol="eigenaar",
            ),
            # the sibling team's node is shared with the team for editing
            SharedAccess(
                source_node_id=world.res["node_sibling"],
                target_eenheid_id=world.org["team"].id,
                access_level="edit",
                geldig_van=date.today() - timedelta(days=1),
            ),
        ]
    )
    await db.flush()
    world.res.update(
        opdracht_elders=opdracht_elders.id,
        task_on_elders_node=task_on_elders_node.id,
        task_assigned=task_assigned.id,
        lead_elders=lead_elders.id,
    )
    return world


# ---------------------------------------------------------------------------
# 1. List, detail and can(read) agree, for everyone on everything
# ---------------------------------------------------------------------------

# (resource type, read permission, list route, detail route, key prefix)
READ_SURFACES = [
    ("corpus_node", "node:read", "/api/nodes?limit=500", "/api/nodes/{}", "node_"),
    ("task", "task:read", "/api/tasks?limit=500", "/api/tasks/{}", "task_"),
    (
        "opdracht",
        "opdracht:read",
        "/api/opdrachten",
        "/api/opdrachten/{}",
        "opdracht_",
    ),
    ("lead", "lead:read", "/api/leads?limit=500", "/api/leads/{}", "lead"),
]


@pytest.mark.parametrize(
    ("resource_type", "permission", "list_path", "detail_path", "prefix"),
    READ_SURFACES,
    ids=[s[0] for s in READ_SURFACES],
)
async def test_list_detail_and_can_read_agree(
    cw, resource_type, permission, list_path, detail_path, prefix
):
    keys = [k for k in cw.res if k.startswith(prefix) and k not in ("lead_column",)]
    mismatches = []
    for who, person in cw.person.items():
        ctx = await perm_ctx(cw, who)
        async with client_as(cw.db, person) as c:
            listed_resp = await c.get(list_path)
            listed = (
                {item["id"] for item in listed_resp.json()}
                if listed_resp.status_code == 200
                else set()
            )
            for key in keys:
                rid = cw.res[key]
                detail = (await c.get(detail_path.format(rid))).status_code
                decided = await can(cw.db, ctx, permission, resource_type, rid)
                row = (str(rid) in listed, detail == 200, decided)
                if len(set(row)) != 1:
                    mismatches.append((who, key, row))
    assert not mismatches, mismatches


# The rows the table above must get right, pinned so they cannot pass by
# everyone seeing nothing.
ROLE_AND_SHARE_READS = [
    ("viewer", "node:read", "corpus_node", "node_elders", True),  # adviseur
    ("viewer", "opdracht:read", "opdracht", "opdracht_elders", True),  # betrokken
    ("viewer", "task:read", "task", "task_on_elders_node", True),  # via its node
    ("viewer", "task:read", "task", "task_assigned", True),  # own task
    ("viewer", "task:read", "task", "task_elders", False),
    ("viewer", "node:read", "corpus_node", "node_sibling", True),  # shared node
    ("team_editor", "node:update", "corpus_node", "node_sibling", True),
    ("viewer", "lead:read", "lead", "lead_elders", False),  # eenheid not visible
    ("elders_editor", "lead:read", "lead", "lead_elders", True),
    ("viewer", "lead:read", "lead", "lead_free", True),  # no initiatief, no eenheid
    ("role_only", "node:read", "corpus_node", "node_directie", True),  # betrokken
    ("role_only", "node:update", "corpus_node", "node_directie", True),
    # without the opdrachten module only a role on the opdracht itself
    # counts, for reading and writing alike
    ("role_only", "opdracht:update", "opdracht", "opdracht_elders", True),
    ("role_only", "opdracht:read", "opdracht", "opdracht_elders", True),
    ("role_only", "opdracht:read", "opdracht", "opdracht_free", False),
]


@pytest.mark.parametrize(
    ("who", "permission", "resource_type", "key", "expected"),
    ROLE_AND_SHARE_READS,
    ids=[f"{c[0]}-{c[1]}-{c[3]}" for c in ROLE_AND_SHARE_READS],
)
async def test_roles_and_shares_make_things_readable(
    cw, who, permission, resource_type, key, expected
):
    ctx = await perm_ctx(cw, who)
    assert await can(cw.db, ctx, permission, resource_type, cw.res[key]) is expected


async def test_whoever_may_write_may_read(cw):
    """For every person and resource: a write decision implies a read one."""
    offenders = []
    for who in cw.person:
        ctx = await perm_ctx(cw, who)
        for key, rid in cw.res.items():
            for resource_type, domain, prefix in (
                ("corpus_node", "node", "node_"),
                ("task", "task", "task_"),
                ("opdracht", "opdracht", "opdracht_"),
                ("lead", "lead", "lead"),
            ):
                if not key.startswith(prefix) or key == "lead_column":
                    continue
                writes = await can(cw.db, ctx, f"{domain}:update", resource_type, rid)
                reads = await can(cw.db, ctx, f"{domain}:read", resource_type, rid)
                if writes and not reads:
                    offenders.append((who, key))
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# 2. Search applies the same rules
# ---------------------------------------------------------------------------


async def _search(w: World, who: str, q: str, result_type: str) -> set[str]:
    async with client_as(w.db, w.person[who]) as c:
        resp = await c.get("/api/search", params={"q": q, "result_types": result_type})
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["results"]}


async def test_search_reads_a_task_without_eenheid_through_its_node(cw):
    """ "Taak zonder eenheid" lives on the team's node: not for an editor elsewhere."""
    task = str(cw.res["task_on_team_node"])
    assert task not in await _search(cw, "elders_editor", "zonder eenheid", "task")
    assert task in await _search(cw, "team_editor", "zonder eenheid", "task")


async def test_search_finds_what_a_role_or_share_makes_visible(cw):
    found = await _search(cw, "viewer", "Dossier", "corpus_node")
    assert str(cw.res["node_elders"]) in found  # adviseur
    assert str(cw.res["node_sibling"]) in found  # shared with the team
    assert str(cw.res["node_free"]) in found
    hidden = await _search(cw, "elders_editor", "Teamdossier", "corpus_node")
    assert str(cw.res["node_team"]) not in hidden


async def test_search_leads_follow_their_eenheid(cw):
    lead = str(cw.res["lead_elders"])
    assert lead not in await _search(cw, "viewer", "Lead elders", "lead")
    assert lead in await _search(cw, "elders_editor", "Lead elders", "lead")


# ---------------------------------------------------------------------------
# 3. One move rule
# ---------------------------------------------------------------------------


def _opdracht_body(w: World, **places) -> dict:
    return {
        "type": "opdracht",
        "titel": "Nieuw",
        "begrotingsjaar": 2026,
        "instrument_id": str(w.res["node_team"]),
        **{k: str(w.org[v].id) for k, v in places.items()},
    }


MOVES = [
    # a task: task:update where it is, task:create where it goes
    (
        "team_editor",
        "PUT",
        "/api/tasks/{task_team}",
        {"organisatie_eenheid_id": "afdeling"},
        403,
    ),
    (
        "afd_editor",
        "PUT",
        "/api/tasks/{task_team}",
        {"organisatie_eenheid_id": "afdeling"},
        200,
    ),
    (
        "afd_editor",
        "PUT",
        "/api/tasks/{task_team}",
        {"organisatie_eenheid_id": "elders"},
        403,
    ),
    # a lead without initiatief: lead:update where it is, lead:create where
    # it goes; making it tenant-wide again is for system roles only
    (
        "elders_editor",
        "PUT",
        "/api/leads/{lead_elders}",
        {"organisatie_eenheid_id": None},
        403,
    ),
    (
        "super_admin",
        "PUT",
        "/api/leads/{lead_elders}",
        {"organisatie_eenheid_id": None},
        200,
    ),
    (
        "elders_editor",
        "PUT",
        "/api/leads/{lead_elders}",
        {"organisatie_eenheid_id": "team"},
        403,
    ),
    (
        "manager",
        "PUT",
        "/api/leads/{lead_elders}",
        {"organisatie_eenheid_id": "team"},
        404,
    ),
]


def _move_body(w: World, body: dict) -> dict:
    return {k: (str(w.org[v].id) if v else None) for k, v in body.items()}


@pytest.mark.parametrize(
    ("who", "method", "path", "body", "expected"),
    MOVES,
    ids=[f"{m[0]}-{m[2]}-{next(iter(m[3].values()))}" for m in MOVES],
)
async def test_moves(cw, who, method, path, body, expected):
    async with client_as(cw.db, cw.person[who]) as c:
        resp = await c.request(method, path.format(**cw.res), json=_move_body(cw, body))
    assert resp.status_code == expected, resp.text


async def test_creating_an_opdracht_needs_every_eenheid_it_names(cw):
    async with client_as(cw.db, cw.person["team_editor"]) as c:
        one_foreign = await c.post(
            "/api/opdrachten",
            json=_opdracht_body(
                cw, opdrachtgever_id="team", opdrachtnemer_eenheid_id="elders"
            ),
        )
        both_own = await c.post(
            "/api/opdrachten",
            json=_opdracht_body(
                cw, opdrachtgever_id="team", opdrachtnemer_eenheid_id="team"
            ),
        )
    assert one_foreign.status_code == 403, one_foreign.text
    assert both_own.status_code == 201, both_own.text


# ---------------------------------------------------------------------------
# 5. Eenheden: deleting is ending; creating an internal eenheid is local
# ---------------------------------------------------------------------------


async def test_deleting_an_eenheid_is_decided_like_dissolving_it(cw):
    """The aanmaker is eigenaar (org:update) but manages no internal eenheid."""
    async with client_as(cw.db, cw.person["team_editor"]) as c:
        internal = await c.post(
            "/api/organisatie",
            json={
                "naam": "Subteam",
                "type": "team",
                "parent_id": str(cw.org["team"].id),
            },
        )
        external = await c.post(
            "/api/organisatie", json={"naam": "Gemeente X", "type": "gemeente"}
        )
        ids = [internal.json()["id"], external.json()["id"]]
        evaluations = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask("eenheid:dissolve", "organisatie_eenheid", i) for i in ids
                ]
            },
        )
        deletes = [(await c.delete(f"/api/organisatie/{i}")).status_code for i in ids]
    assert internal.status_code == 201 and external.status_code == 201
    assert [e["decision"] for e in evaluations.json()["evaluations"]] == [False, True]
    assert deletes == [403, 204]


# ---------------------------------------------------------------------------
# 6. No existence oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/nodes/{node_elders}", 404),  # not visible: as if missing
        ("/api/nodes/{node_directie}", 403),  # visible above, not writable
    ],
)
async def test_refused_write_hides_what_you_cannot_see(cw, path, expected):
    async with client_as(cw.db, cw.person["team_editor"]) as c:
        resp = await c.put(path.format(**cw.res), json={"title": "Nee"})
    assert resp.status_code == expected, resp.text


# ---------------------------------------------------------------------------
# 7a. Grants to an eenheid, asked like the routes decide them
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["afd_editor", "team_editor", "role_only", "manager"])
async def test_evaluation_grants_to_an_eenheid_like_the_guard(cw, who):
    initiatief = cw.res["initiatief"]
    target = cw.org["elders"].id
    ctx = await perm_ctx(cw, who)
    try:
        await authority.require_can_grant_resource_role(
            cw.db,
            ctx,
            resource_type="initiatief",
            resource_id=initiatief,
            rol="contributor",
            target_eenheid_id=target,
        )
        expected = True
    except Exception:  # noqa: BLE001 - any refusal is "no"
        expected = False
    async with client_as(cw.db, cw.person[who]) as c:
        resp = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask(
                        "resource_role:grant",
                        "initiatief",
                        initiatief,
                        rol="contributor",
                        target_eenheid_id=target,
                    )
                ]
            },
        )
    assert resp.json()["evaluations"][0]["decision"] is expected


async def test_evaluation_revokes_a_grant_of_an_eenheid(iw):
    question = ask(
        "resource_role:revoke",
        "initiatief",
        iw.res["initiatief"],
        target_eenheid_id=iw.org["partner"].id,
    )
    answers = {}
    for who in ("afd_editor", "viewer"):
        async with client_as(iw.db, iw.person[who]) as c:
            resp = await c.post(
                "/api/authz/evaluations", json={"evaluations": [question]}
            )
        answers[who] = resp.json()["evaluations"][0]["decision"]
    # the owning afdeling manages the grants, a bystander does not
    assert answers["afd_editor"] is True
    assert answers["viewer"] is False


# ---------------------------------------------------------------------------
# 7b. GET /api/authz/eenheden equals asking per eenheid
# ---------------------------------------------------------------------------


def _per_eenheid_question(action: str, eenheid_id) -> dict:
    if action in ("org:update", "org:manage"):
        return ask(action, "organisatie_eenheid", eenheid_id)
    if action == "org:create":
        return ask(action, "organisatie_eenheid", eenheid_id=eenheid_id)
    if action == "people:assign_role":
        return ask("role:assign", "role", anywhere=True, eenheid_id=eenheid_id)
    return ask("person:place", "person", eenheid_id=eenheid_id)


@pytest.mark.parametrize(
    "action",
    ["org:manage", "org:update", "org:create", "people:assign_role", "person:place"],
)
async def test_eenheden_endpoint_equals_the_evaluations(iw, action):
    # a synced eenheid below the directie: read-only for org:update/manage
    synced = OrganisatieEenheid(
        naam="TOOI-team", type="team", parent_id=iw.org["afdeling"].id, bron="tooi"
    )
    iw.db.add(synced)
    await iw.db.flush()
    eenheden = [*(o.id for o in iw.org.values()), synced.id]
    for who, person in iw.person.items():
        async with client_as(iw.db, person) as c:
            listed = await c.get("/api/authz/eenheden", params={"action": action})
            asked = await c.post(
                "/api/authz/evaluations",
                json={
                    "evaluations": [_per_eenheid_question(action, e) for e in eenheden]
                },
            )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        decisions = [d["decision"] for d in asked.json()["evaluations"]]
        if body["all"]:
            assert all(decisions), (who, action)
            continue
        ids = set(body["ids"])
        got = [str(e) in ids for e in eenheden]
        assert got == decisions, (who, action, got, decisions)


async def test_eenheden_endpoint_rejects_other_actions(cw):
    async with client_as(cw.db, cw.person["viewer"]) as c:
        resp = await c.get("/api/authz/eenheden", params={"action": "node:update"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 7c. Deciding many things over many eenheden costs constant queries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [3, 30])
async def test_prefetch_loads_chains_in_one_query(world, count):
    db = world.db
    ids = []
    parent = world.org["afdeling"]
    for i in range(count):
        # each node in its own eenheid, each eenheid one level deeper
        parent = await make_org(db, f"Laag {i}", "team", parent)
        node = CorpusNode(
            title=f"Node {i}",
            node_type="dossier",
            status="actief",
            organisatie_eenheid_id=parent.id,
        )
        db.add(node)
        await db.flush()
        ids.append(node.id)
    ctx = await perm_ctx(world, "afd_editor")
    queries = 0

    def _count(*_args):
        nonlocal queries
        queries += 1

    event.listen(db.sync_session, "do_orm_execute", _count)
    try:
        await prefetch(db, ctx, "corpus_node", ids)
        after_prefetch = queries
        decisions = [await can(db, ctx, "node:update", "corpus_node", i) for i in ids]
    finally:
        event.remove(db.sync_session, "do_orm_execute", _count)
    assert all(decisions)
    assert after_prefetch <= 2  # locations, chains
    assert queries - after_prefetch <= 1  # the edit shares, once
