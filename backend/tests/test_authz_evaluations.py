# ruff: noqa: F811  (tests take the imported ``world`` fixture)
"""Grant actions and "anywhere" on the evaluation endpoint.

Builds on ``test_authz.world``; adds a ministry_admin scoped to the
directie, who may assign roles below it but writes no nodes.  Grant actions
are answered by the ``core.authority`` guards, so each case here mirrors a
route test in ``test_grant_authority``.
"""

import pytest
from sqlalchemy import select

from bouwmeester.models.role import PersonRole
from tests.factories import client_as, grant_role, make_person, place
from tests.test_authz import World, _ask, world  # noqa: F401


@pytest.fixture
async def ew(world: World) -> World:
    admin = await make_person(world.db, "Ministeriebeheerder")
    await place(world.db, admin, world.org["directie"])
    await grant_role(world.db, admin, "ministry_admin", world.org["directie"])
    world.person["ministry_admin"] = admin
    return world


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
        lambda w: _ask(
            "role:assign", "role", role_id="editor", eenheid_id=_org(w, "team")
        ),
        True,
    ),
    (
        "ministry_admin",
        lambda w: _ask(
            "role:assign", "role", role_id="editor", eenheid_id=_org(w, "elders")
        ),
        False,
    ),
    (
        "ministry_admin",
        lambda w: _ask(
            "role:assign", "role", role_id="ministry_admin", eenheid_id=_org(w, "team")
        ),
        False,
    ),
    (
        "ministry_admin",
        lambda w: _ask(
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
        lambda w: _ask(
            "role:assign", "role", role_id="editor", eenheid_id=_org(w, "team")
        ),
        False,
    ),
    (
        "super_admin",
        lambda w: _ask("role:assign", "role", role_id="platform_admin"),
        True,
    ),
    (
        "ministry_admin",
        lambda w: _ask("role:assign", "role", role_id="onbekend"),
        False,
    ),
    # naming a manager is assigning unit_manager
    (
        "ministry_admin",
        lambda w: _ask("eenheid:set_manager", "organisatie_eenheid", _org(w, "team")),
        True,
    ),
    (
        "manager",
        lambda w: _ask("eenheid:set_manager", "organisatie_eenheid", _org(w, "team")),
        False,
    ),
    # placing an account is the manager's call; editors file a request
    (
        "manager",
        lambda w: _ask("person:place", "person", eenheid_id=_org(w, "team")),
        True,
    ),
    (
        "team_editor",
        lambda w: _ask("person:place", "person", eenheid_id=_org(w, "team")),
        False,
    ),
    (
        "team_editor",
        lambda w: _ask(
            "person:place", "person", _person(w, "viewer"), eenheid_id=_org(w, "team")
        ),
        False,
    ),
    # dissolving an internal eenheid needs its manager
    (
        "manager",
        lambda w: _ask("eenheid:dissolve", "organisatie_eenheid", _org(w, "team")),
        True,
    ),
    (
        "team_editor",
        lambda w: _ask("eenheid:dissolve", "organisatie_eenheid", _org(w, "team")),
        False,
    ),
    # resource roles: resource_permission:manage on the owning eenheid (or
    # above it), not for yourself, only the type's own rols
    (
        "manager",
        lambda w: _ask(
            "resource_role:grant", "initiatief", w.res["initiatief"], rol="contributor"
        ),
        True,
    ),
    (
        "manager",
        lambda w: _ask(
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
        lambda w: _ask(
            "resource_role:grant", "initiatief", w.res["initiatief"], rol="viewer"
        ),
        False,
    ),
    (
        "afd_editor",
        lambda w: _ask(
            "resource_role:grant", "initiatief", w.res["initiatief"], rol="x"
        ),
        False,
    ),
    # lead contacts: an editor of the lead, opdrachtgever never to yourself
    (
        "role_only",
        lambda w: _ask(
            "resource_role:grant", "lead", w.res["lead"], rol="opdrachtgever"
        ),
        True,
    ),
    (
        "role_only",
        lambda w: _ask(
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
    ("who", "ask", "expected"),
    GRANT_CASES,
    ids=[f"{c[0]}-{i}" for i, c in enumerate(GRANT_CASES)],
)
async def test_grant_actions_ask_the_authority_guards(ew, who, ask, expected):
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [ask(ew)]})
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
    ask = _ask("role:revoke", "role", assignment_id)
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": [ask]})
    assert resp.json() == {"evaluations": [{"decision": expected}]}


# (who, action, resource type, expected with anywhere=true)
ANYWHERE_CASES = [
    ("team_editor", "task:create", "task", True),
    ("manager", "task:create", "task", True),
    ("viewer", "task:create", "task", False),
    ("role_only", "task:create", "task", False),
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
        _ask(action, resource_type, anywhere=True),
        # without anywhere a task needs an eenheid: no eenheid is no
        _ask(action, resource_type),
    ]
    async with client_as(ew.db, ew.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json={"evaluations": asks})
    assert resp.status_code == 200, resp.text
    anywhere, nowhere = (e["decision"] for e in resp.json()["evaluations"])
    assert anywhere is expected
    if resource_type == "task" and who != "super_admin":
        assert nowhere is False
