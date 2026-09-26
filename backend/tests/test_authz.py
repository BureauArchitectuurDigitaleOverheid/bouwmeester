"""The single decision point (``core/authz.py``).

A realistic tree (ministerie > DG > directie > afdeling > team) with mixed
roles and real permission resolution.  One table covers each resolution
step; a few route and chat tests check that the reference migration
(nodes, edges, tasks) asks the same question.
"""

import uuid
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can, require
from bouwmeester.core.org_context import build_org_context
from bouwmeester.core.permissions import PermissionContext, build_permission_context
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.models.task import Task
from bouwmeester.repositories.lead_column import LeadColumnRepository
from tests.factories import client_as, grant_role, make_org, make_person, place


@dataclass
class World:
    db: AsyncSession
    org: dict[str, OrganisatieEenheid]
    person: dict[str, Person]
    res: dict[str, uuid.UUID]


async def _node(db: AsyncSession, title: str, eenheid=None) -> CorpusNode:
    node = CorpusNode(
        id=uuid.uuid4(),
        title=title,
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=eenheid.id if eenheid else None,
    )
    db.add(node)
    await db.flush()
    return node


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    db = db_session
    ministerie = await make_org(db, "Ministerie", "ministerie")
    dg = await make_org(db, "DG", "directoraat_generaal", ministerie)
    directie = await make_org(db, "Directie", "directie", dg)
    afdeling = await make_org(db, "Afdeling", "afdeling", directie)
    team = await make_org(db, "Team", "team", afdeling)
    elders = await make_org(db, "Elders", "directie", dg)
    sibling_team = await make_org(db, "Ander team", "team", afdeling)

    # Only super_admin and platform_admin exist as system roles.
    platform_admin = await make_person(db, "Platformbeheerder")
    await grant_role(db, platform_admin, "platform_admin")

    afd_editor = await make_person(db, "Afdelingsredacteur")
    await place(db, afd_editor, afdeling)
    await grant_role(db, afd_editor, "editor", afdeling)

    team_editor = await make_person(db, "Teamredacteur")
    await place(db, team_editor, team)
    await grant_role(db, team_editor, "editor", team)

    viewer = await make_person(db, "Teamlid")  # implicit viewer
    await place(db, viewer, team)

    role_only = await make_person(db, "Alleen resource-rol")
    manager = await make_person(db, "Directeur")
    await place(db, manager, directie)
    await grant_role(db, manager, "unit_manager", directie)

    super_admin = await make_person(db, "Systeembeheerder")
    await grant_role(db, super_admin, "super_admin")

    node_directie = await _node(db, "Directiedossier", directie)
    node_afdeling = await _node(db, "Afdelingsdossier", afdeling)
    node_team = await _node(db, "Teamdossier", team)
    node_elders = await _node(db, "Dossier elders", elders)
    node_free = await _node(db, "Dossier zonder eenheid")
    node_sibling = await _node(db, "Dossier ander team", sibling_team)
    opdracht_free = Opdracht(type="opdracht", titel="FCC-import", begrotingsjaar=2026)
    opdracht_directie = Opdracht(
        type="opdracht",
        titel="Directie-opdracht",
        begrotingsjaar=2026,
        opdrachtgever_id=directie.id,
    )
    samenwerkingsverband = Samenwerkingsverband(naam="Werkgroep", type="werkgroep")
    db.add_all([opdracht_free, opdracht_directie, samenwerkingsverband])
    db.add(
        ResourcePermission(
            person_id=role_only.id,
            resource_type="corpus_node",
            resource_id=node_directie.id,
            rol="betrokken",
        )
    )

    et = EdgeType(id=f"authz_{uuid.uuid4().hex[:8]}", label_nl="T", label_en="T")
    db.add(et)
    await db.flush()
    edge_team_directie = Edge(
        from_node_id=node_team.id, to_node_id=node_directie.id, edge_type_id=et.id
    )
    edge_directie_elders = Edge(
        from_node_id=node_directie.id, to_node_id=node_elders.id, edge_type_id=et.id
    )
    db.add_all([edge_team_directie, edge_directie_elders])

    task_team = Task(
        title="Teamtaak",
        node_id=node_directie.id,
        organisatie_eenheid_id=team.id,
        status="open",
    )
    task_on_team_node = Task(
        title="Taak zonder eenheid", node_id=node_team.id, status="open"
    )
    db.add_all([task_team, task_on_team_node])

    initiatief = Initiatief(id=uuid.uuid4(), naam=f"Init {uuid.uuid4().hex[:6]}")
    db.add(initiatief)
    await db.flush()
    db.add_all(
        [
            ResourcePermission(
                organisatie_eenheid_id=afdeling.id,
                resource_type="initiatief",
                resource_id=initiatief.id,
                rol="eigenaar",
            ),
            ResourcePermission(
                person_id=role_only.id,
                resource_type="initiatief",
                resource_id=initiatief.id,
                rol="contributor",
            ),
        ]
    )
    lead = Lead(title="Lead", stage="verkennen", initiatief_id=initiatief.id)
    lead_free = Lead(title="Losse lead", stage="verkennen")
    db.add_all([lead, lead_free])
    await db.flush()
    await LeadColumnRepository(db).seed_defaults(initiatief.id)
    column = await db.scalar(
        select(LeadColumn.id).where(LeadColumn.initiatief_id == initiatief.id).limit(1)
    )

    return World(
        db=db,
        org={
            "ministerie": ministerie,
            "dg": dg,
            "directie": directie,
            "afdeling": afdeling,
            "team": team,
            "elders": elders,
            "sibling_team": sibling_team,
        },
        person={
            "platform_admin": platform_admin,
            "afd_editor": afd_editor,
            "team_editor": team_editor,
            "viewer": viewer,
            "role_only": role_only,
            "manager": manager,
            "super_admin": super_admin,
        },
        res={
            "eenheid_elders": elders.id,
            "eenheid_team": team.id,
            "node_directie": node_directie.id,
            "node_afdeling": node_afdeling.id,
            "node_team": node_team.id,
            "node_elders": node_elders.id,
            "node_free": node_free.id,
            "node_sibling": node_sibling.id,
            "opdracht_free": opdracht_free.id,
            "samenwerkingsverband": samenwerkingsverband.id,
            "opdracht_directie": opdracht_directie.id,
            "edge_team_directie": edge_team_directie.id,
            "edge_directie_elders": edge_directie_elders.id,
            "task_team": task_team.id,
            "task_on_team_node": task_on_team_node.id,
            "initiatief": initiatief.id,
            "lead": lead.id,
            "lead_free": lead_free.id,
            "lead_column": column,
        },
    )


async def _ctx(w: World, who: str) -> PermissionContext:
    return await build_permission_context(w.db, w.person[who])


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
    ("team_editor", "tag:create", "corpus_node", "node_free", None, True),
    ("team_editor", "tag:create", "corpus_node", "node_directie", None, False),
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


@pytest.mark.parametrize(
    ("who", "permission", "resource_type", "resource", "eenheid", "expected"),
    CASES,
    ids=[f"{c[0]}-{c[1]}-{c[3] or c[4] or 'new'}" for c in CASES],
)
async def test_can(world, who, permission, resource_type, resource, eenheid, expected):
    ctx = await _ctx(world, who)
    resource_id = world.res[resource] if resource else None
    eenheid_id = world.org[eenheid].id if eenheid else None
    got = await can(
        world.db, ctx, permission, resource_type, resource_id, eenheid_id=eenheid_id
    )
    assert got is expected


async def test_visible_is_not_writable(world):
    """A team editor sees the directie above the team, but cannot write there."""
    ctx = await _ctx(world, "team_editor")
    org_ctx = await build_org_context(
        world.db, world.person["team_editor"], perm_ctx=ctx
    )
    assert world.org["directie"].id in org_ctx.visible_eenheid_ids
    assert not await can(
        world.db, ctx, "node:update", "corpus_node", world.res["node_directie"]
    )


async def test_require_raises_404_403_401(world):
    ctx = await _ctx(world, "team_editor")
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
    ctx = await _ctx(world, "super_admin")
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
    editor = await _ctx(world, "team_editor")
    viewer = await _ctx(world, "viewer")
    node = world.res["node_directie"]
    assert await can(world.db, editor, "node:update", "corpus_node", node) is expected
    assert not await can(world.db, viewer, "node:update", "corpus_node", node)


# ---------------------------------------------------------------------------
# Reference migration: routes and chat ask the same question
# ---------------------------------------------------------------------------


async def test_route_update_node_follows_authz(world):
    async with client_as(world.db, world.person["team_editor"]) as c:
        denied = await c.put(
            f"/api/nodes/{world.res['node_directie']}", json={"title": "Nee"}
        )
        allowed = await c.put(
            f"/api/nodes/{world.res['node_team']}", json={"title": "Ja"}
        )
        missing = await c.put(f"/api/nodes/{uuid.uuid4()}", json={"title": "?"})
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert missing.status_code == 404


async def test_route_create_edge_needs_one_writable_end(world):
    edge_type = await world.db.scalar(
        select(Edge.edge_type_id).where(Edge.id == world.res["edge_team_directie"])
    )
    async with client_as(world.db, world.person["team_editor"]) as c:
        into_team = await c.post(
            "/api/edges",
            json={
                "from_node_id": str(world.res["node_directie"]),
                "to_node_id": str(world.res["node_team"]),
                "edge_type_id": edge_type,
            },
        )
        between_others = await c.post(
            "/api/edges",
            json={
                "from_node_id": str(world.res["node_afdeling"]),
                "to_node_id": str(world.res["node_directie"]),
                "edge_type_id": edge_type,
            },
        )
    assert into_team.status_code == 201, into_team.text
    assert between_others.status_code == 403


async def test_route_create_task_checks_target_eenheid(world):
    async with client_as(world.db, world.person["afd_editor"]) as c:
        in_team = await c.post(
            "/api/tasks",
            json={
                "title": "Mag",
                "node_id": str(world.res["node_directie"]),
                "organisatie_eenheid_id": str(world.org["team"].id),
            },
        )
        in_directie = await c.post(
            "/api/tasks",
            json={
                "title": "Mag niet",
                "node_id": str(world.res["node_team"]),
                "organisatie_eenheid_id": str(world.org["directie"].id),
            },
        )
        moved_up = await c.put(
            f"/api/tasks/{world.res['task_team']}",
            json={"organisatie_eenheid_id": str(world.org["directie"].id)},
        )
    assert in_team.status_code == 201, in_team.text
    assert in_directie.status_code == 403
    assert moved_up.status_code == 403


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


# ---------------------------------------------------------------------------
# Visibility follows write rights downward
# ---------------------------------------------------------------------------


async def test_afdeling_editor_sees_team_resources_below(world):
    """Rights inherit downward, so the afdeling editor also sees team items."""
    ctx = await _ctx(world, "afd_editor")
    org_ctx = await build_org_context(
        world.db, world.person["afd_editor"], perm_ctx=ctx
    )
    assert world.org["team"].id in org_ctx.visible_eenheid_ids
    async with client_as(world.db, world.person["afd_editor"]) as c:
        detail = await c.get(f"/api/nodes/{world.res['node_team']}")
        listing = await c.get("/api/nodes", params={"search": "Teamdossier"})
    assert detail.status_code == 200
    assert str(world.res["node_team"]) in {n["id"] for n in listing.json()}


async def test_team_member_does_not_see_sibling_team(world):
    ctx = await _ctx(world, "viewer")
    org_ctx = await build_org_context(world.db, world.person["viewer"], perm_ctx=ctx)
    assert world.org["sibling_team"].id not in org_ctx.visible_eenheid_ids
    async with client_as(world.db, world.person["viewer"]) as c:
        detail = await c.get(f"/api/nodes/{world.res['node_sibling']}")
    assert detail.status_code == 404


async def test_team_editor_does_not_see_sibling_team(world):
    """Writing in a team does not open up the teams next to it."""
    ctx = await _ctx(world, "team_editor")
    org_ctx = await build_org_context(
        world.db, world.person["team_editor"], perm_ctx=ctx
    )
    assert world.org["sibling_team"].id not in org_ctx.visible_eenheid_ids


# ---------------------------------------------------------------------------
# POST /api/authz/evaluations
# ---------------------------------------------------------------------------


def _ask(action: str, resource_type: str, resource_id=None, **properties) -> dict:
    resource: dict = {"type": resource_type}
    if resource_id is not None:
        resource["id"] = str(resource_id)
    if properties:
        resource["properties"] = {
            k: v if isinstance(v, bool) else str(v) for k, v in properties.items()
        }
    return {"action": action, "resource": resource}


async def test_evaluations_answer_in_order(world):
    asks = [
        _ask("node:update", "corpus_node", world.res["node_team"]),
        _ask("node:update", "corpus_node", world.res["node_directie"]),
        _ask("edge:update", "edge", world.res["edge_team_directie"]),
        _ask("task:create", "task", eenheid_id=world.org["team"].id),
        _ask("node:create", "corpus_node"),
    ]
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "evaluations": [
            {"decision": True},
            {"decision": False},
            {"decision": True},
            {"decision": True},
            {"decision": True},
        ]
    }


async def test_evaluations_missing_resource_is_false_not_404(world):
    asks = [
        _ask("node:update", "corpus_node", uuid.uuid4()),
        _ask("edge:delete", "edge", uuid.uuid4()),
    ]
    async with client_as(world.db, world.person["super_admin"]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
    assert resp.status_code == 200
    assert resp.json() == {"evaluations": [{"decision": False}, {"decision": False}]}


@pytest.mark.parametrize(
    "body",
    [
        {"evaluations": []},
        {"evaluations": [_ask("node:read", "corpus_node")] * 51},
        {"evaluations": [_ask("node:read", "onbekend_type")]},
        {"evaluations": [{"action": "node:read", "resource": {"type": "x"}}]},
        {"evaluations": [_ask("node read", "corpus_node")]},
        {
            "subject": {"type": "user", "id": str(uuid.uuid4())},
            "evaluations": [_ask("node:read", "corpus_node")],
        },
        {
            "evaluations": [
                {
                    **_ask("node:read", "corpus_node"),
                    "subject": {"type": "user", "id": str(uuid.uuid4())},
                }
            ]
        },
    ],
    ids=[
        "empty",
        "too-many",
        "unknown-type",
        "bad-type",
        "bad-action",
        "subject-top",
        "subject-item",
    ],
)
async def test_evaluations_reject_bad_input(world, body):
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post("/api/authz/evaluations", json=body)
    assert resp.status_code == 422


def test_evaluations_endpoint_is_not_public():
    from bouwmeester.middleware.auth_required import is_public_path

    assert not is_public_path("/api/authz/evaluations")


async def test_existing_person_is_not_decided_here(world):
    ctx = await _ctx(world, "team_editor")
    with pytest.raises(ValueError):
        await can(world.db, ctx, "people:update", "person", world.person["viewer"].id)
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    _ask("people:update", "person", world.person["viewer"].id),
                    _ask("people:create", "person"),
                ]
            },
        )
    assert resp.json() == {"evaluations": [{"decision": False}, {"decision": True}]}
