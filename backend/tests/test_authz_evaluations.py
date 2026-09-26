"""``POST /api/authz/evaluations``: the frontend's question to ``core.authz``.

Uses the shared tree of ``tests/authz_world.py``; ``ew`` adds a
ministry_admin scoped to the directie, who may assign roles below it but
writes no nodes.  Grant actions are answered by the ``core.authority``
guards, so each of those cases mirrors a route test in
``test_grant_authority``.
"""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import can
from bouwmeester.models.role import PersonRole
from tests.authz_world import World, add_directie_admin, ask, perm_ctx
from tests.factories import client_as


@pytest.fixture
async def ew(world: World) -> World:
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    return world


# ---------------------------------------------------------------------------
# can() actions: answered in order, a missing resource is false
# ---------------------------------------------------------------------------


async def test_evaluations_answer_in_order(world):
    asks = [
        ask("node:update", "corpus_node", world.res["node_team"]),
        ask("node:update", "corpus_node", world.res["node_directie"]),
        ask("edge:update", "edge", world.res["edge_team_directie"]),
        ask("task:create", "task", eenheid_id=world.org["team"].id),
        ask("node:create", "corpus_node"),
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
        ask("node:update", "corpus_node", uuid.uuid4()),
        ask("edge:delete", "edge", uuid.uuid4()),
    ]
    async with client_as(world.db, world.person["super_admin"]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
    assert resp.status_code == 200
    assert resp.json() == {"evaluations": [{"decision": False}, {"decision": False}]}


@pytest.mark.parametrize(
    "body",
    [
        {"evaluations": []},
        {"evaluations": [ask("node:read", "corpus_node")] * 51},
        {"evaluations": [ask("node:read", "onbekend_type")]},
        {"evaluations": [{"action": "node:read", "resource": {"type": "x"}}]},
        {"evaluations": [ask("node read", "corpus_node")]},
        {
            "subject": {"type": "user", "id": str(uuid.uuid4())},
            "evaluations": [ask("node:read", "corpus_node")],
        },
        {
            "evaluations": [
                {
                    **ask("node:read", "corpus_node"),
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
    ctx = await perm_ctx(world, "team_editor")
    with pytest.raises(ValueError):
        await can(world.db, ctx, "people:update", "person", world.person["viewer"].id)
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask("people:update", "person", world.person["viewer"].id),
                    ask("people:create", "person"),
                ]
            },
        )
    assert resp.json() == {"evaluations": [{"decision": False}, {"decision": True}]}


# ---------------------------------------------------------------------------
# Grant actions: the core.authority guards
# ---------------------------------------------------------------------------


def _org(w: World, key: str):
    return w.org[key].id


def _person(w: World, key: str):
    return w.person[key].id


# (who, evaluation builder, expected decision)
GRANT_CASES = [
    # role:assign follows _require_role_authority: people:assign_role on the
    # eenheid, rank below your own, never to yourself
    (
        "ministry_admin",
        lambda w: ask(
            "role:assign", "role", role_id="editor", eenheid_id=_org(w, "team")
        ),
        True,
    ),
    (
        "ministry_admin",
        lambda w: ask(
            "role:assign", "role", role_id="editor", eenheid_id=_org(w, "elders")
        ),
        False,
    ),
    (
        "ministry_admin",
        lambda w: ask(
            "role:assign", "role", role_id="ministry_admin", eenheid_id=_org(w, "team")
        ),
        False,
    ),
    (
        "ministry_admin",
        lambda w: ask(
            "role:assign",
            "role",
            role_id="editor",
            eenheid_id=_org(w, "team"),
            target_person_id=_person(w, "ministry_admin"),
        ),
        False,
    ),
    (
        "manager",
        lambda w: ask(
            "role:assign", "role", role_id="editor", eenheid_id=_org(w, "team")
        ),
        False,
    ),
    (
        "super_admin",
        lambda w: ask("role:assign", "role", role_id="platform_admin"),
        True,
    ),
    (
        "ministry_admin",
        lambda w: ask("role:assign", "role", role_id="onbekend"),
        False,
    ),
    # naming a manager is assigning unit_manager
    (
        "ministry_admin",
        lambda w: ask("eenheid:set_manager", "organisatie_eenheid", _org(w, "team")),
        True,
    ),
    (
        "manager",
        lambda w: ask("eenheid:set_manager", "organisatie_eenheid", _org(w, "team")),
        False,
    ),
    # placing an account is the manager's call; editors file a request
    (
        "manager",
        lambda w: ask("person:place", "person", eenheid_id=_org(w, "team")),
        True,
    ),
    (
        "team_editor",
        lambda w: ask("person:place", "person", eenheid_id=_org(w, "team")),
        False,
    ),
    (
        "team_editor",
        lambda w: ask(
            "person:place", "person", _person(w, "viewer"), eenheid_id=_org(w, "team")
        ),
        False,
    ),
    # dissolving an internal eenheid needs its manager
    (
        "manager",
        lambda w: ask("eenheid:dissolve", "organisatie_eenheid", _org(w, "team")),
        True,
    ),
    (
        "team_editor",
        lambda w: ask("eenheid:dissolve", "organisatie_eenheid", _org(w, "team")),
        False,
    ),
    # resource roles: resource_permission:manage on the owning eenheid (or
    # above it), not for yourself, only the type's own rols
    (
        "manager",
        lambda w: ask(
            "resource_role:grant", "initiatief", w.res["initiatief"], rol="contributor"
        ),
        True,
    ),
    (
        "manager",
        lambda w: ask(
            "resource_role:grant",
            "initiatief",
            w.res["initiatief"],
            rol="contributor",
            target_person_id=_person(w, "manager"),
        ),
        False,
    ),
    (
        "viewer",
        lambda w: ask(
            "resource_role:grant", "initiatief", w.res["initiatief"], rol="viewer"
        ),
        False,
    ),
    (
        "afd_editor",
        lambda w: ask(
            "resource_role:grant", "initiatief", w.res["initiatief"], rol="x"
        ),
        False,
    ),
    # lead contacts: an editor of the lead, opdrachtgever never to yourself
    (
        "role_only",
        lambda w: ask(
            "resource_role:grant", "lead", w.res["lead"], rol="opdrachtgever"
        ),
        True,
    ),
    (
        "role_only",
        lambda w: ask(
            "resource_role:grant",
            "lead",
            w.res["lead"],
            rol="opdrachtgever",
            target_person_id=_person(w, "role_only"),
        ),
        False,
    ),
]


@pytest.mark.parametrize(
    ("who", "build", "expected"),
    GRANT_CASES,
    ids=[f"{c[0]}-{i}" for i, c in enumerate(GRANT_CASES)],
)
async def test_grant_actions_ask_the_authority_guards(ew, who, build, expected):
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [build(ew)]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"evaluations": [{"decision": expected}]}


@pytest.mark.parametrize(
    ("who", "holder", "role_id", "expected"),
    [
        ("ministry_admin", "team_editor", "editor", True),
        ("manager", "team_editor", "editor", False),  # no people:assign_role
        ("team_editor", "team_editor", "editor", True),  # stepping down
        ("super_admin", "super_admin", "super_admin", False),  # last-admin lock
    ],
)
async def test_role_revoke_asks_the_revoke_guard(ew, who, holder, role_id, expected):
    assignment_id = await ew.db.scalar(
        select(PersonRole.id).where(
            PersonRole.person_id == ew.person[holder].id,
            PersonRole.role_id == role_id,
        )
    )
    question = ask("role:revoke", "role", assignment_id)
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [question]})
    assert resp.json() == {"evaluations": [{"decision": expected}]}


# (who, action, resource type, expected with anywhere=true)
ANYWHERE_CASES = [
    ("team_editor", "task:create", "task", True),
    ("manager", "task:create", "task", True),
    ("viewer", "task:create", "task", False),
    # a node role that grants node:update: a task on that node
    ("role_only", "task:create", "task", True),
    # a contributor on an initiatief: a lead in it
    ("role_only", "lead:create", "lead", True),
    ("platform_admin", "task:create", "task", False),
    ("super_admin", "task:create", "task", True),
    ("team_editor", "lead:create", "lead", True),
    ("viewer", "lead:create", "lead", False),
]


@pytest.mark.parametrize(
    ("who", "action", "resource_type", "expected"),
    ANYWHERE_CASES,
    ids=[f"{c[0]}-{c[1]}" for c in ANYWHERE_CASES],
)
async def test_anywhere_asks_every_eenheid(ew, who, action, resource_type, expected):
    asks = [
        ask(action, resource_type, anywhere=True),
        # without anywhere a task needs an eenheid: no eenheid is no
        ask(action, resource_type),
    ]
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
    assert resp.status_code == 200, resp.text
    anywhere, nowhere = (e["decision"] for e in resp.json()["evaluations"])
    assert anywhere is expected
    if resource_type == "task" and who != "super_admin":
        assert nowhere is False


# ---------------------------------------------------------------------------
# person:place variants, resource_role:revoke, role:assign anywhere
# ---------------------------------------------------------------------------

# (who, evaluation builder, expected decision)
MORE_GRANT_CASES = [
    # a contact without account: contact administration, people:update
    (
        "team_editor",
        lambda w: ask(
            "person:place", "person", eenheid_id=_org(w, "team"), contact=True
        ),
        True,
    ),
    (
        "platform_admin",  # holds no people:update
        lambda w: ask(
            "person:place", "person", eenheid_id=_org(w, "team"), contact=True
        ),
        False,
    ),
    # ending your own placement only gives access up
    (
        "team_editor",
        lambda w: ask(
            "person:place",
            "person",
            _person(w, "team_editor"),
            eenheid_id=_org(w, "team"),
            ending=True,
        ),
        True,
    ),
    # any role to someone else, anywhere or in one eenheid
    ("ministry_admin", lambda w: ask("role:assign", "role", anywhere=True), True),
    (
        "ministry_admin",
        lambda w: ask(
            "role:assign", "role", anywhere=True, eenheid_id=_org(w, "elders")
        ),
        False,
    ),
    ("team_editor", lambda w: ask("role:assign", "role", anywhere=True), False),
    ("super_admin", lambda w: ask("role:assign", "role", anywhere=True), True),
    # removing a rol: yourself yes, someone else's only with authority
    (
        "role_only",
        lambda w: ask(
            "resource_role:revoke",
            "corpus_node",
            w.res["node_directie"],
            target_person_id=_person(w, "role_only"),
            rol="betrokken",
        ),
        True,
    ),
    (
        "team_editor",
        lambda w: ask(
            "resource_role:revoke",
            "corpus_node",
            w.res["node_directie"],
            target_person_id=_person(w, "role_only"),
        ),
        False,
    ),
    (
        "super_admin",
        lambda w: ask(
            "resource_role:revoke",
            "corpus_node",
            w.res["node_directie"],
            target_person_id=_person(w, "role_only"),
        ),
        True,
    ),
    (
        "super_admin",  # no such grant
        lambda w: ask(
            "resource_role:revoke",
            "corpus_node",
            w.res["node_team"],
            target_person_id=_person(w, "role_only"),
        ),
        False,
    ),
]


@pytest.mark.parametrize(
    ("who", "build", "expected"),
    MORE_GRANT_CASES,
    ids=[f"{c[0]}-{i}" for i, c in enumerate(MORE_GRANT_CASES)],
)
async def test_more_grant_actions(ew, who, build, expected):
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [build(ew)]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"evaluations": [{"decision": expected}]}


async def test_the_last_eigenaar_cannot_leave(ew):
    from bouwmeester.models.resource_permission import ResourcePermission

    ew.db.add(
        ResourcePermission(
            person_id=_person(ew, "viewer"),
            resource_type="corpus_node",
            resource_id=ew.res["node_free"],
            rol="eigenaar",
        )
    )
    await ew.db.flush()
    question = ask(
        "resource_role:revoke",
        "corpus_node",
        ew.res["node_free"],
        target_person_id=_person(ew, "viewer"),
        rol="eigenaar",
    )
    async with client_as(ew.db, ew.person["viewer"]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [question]})
    assert resp.json() == {"evaluations": [{"decision": False}]}
