"""``POST /api/authz/evaluations``: the frontend's question to ``core.authz``.

Uses the shared tree of ``tests/authz_world.py``; ``ew`` adds a
ministry_admin scoped to the directie, who may assign roles below it but
writes no nodes.  Grant actions are answered by the ``core.authority``
guards, so each of those rows mirrors a route test in ``test_grant_authority``.
"""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.core import authority
from bouwmeester.core.authz import can
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.role import PersonRole
from tests.authz_world import (
    World,
    add,
    add_directie_admin,
    ask,
    evaluate,
    perm_ctx,
    rp,
)
from tests.factories import client_as


@pytest.fixture
async def ew(world: World) -> World:
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    return world


async def test_evaluations_answer_in_order(world):
    got = await evaluate(
        world,
        "team_editor",
        ask("node:update", "corpus_node", "{node_team}"),
        ask("node:update", "corpus_node", "{node_directie}"),
        ask("edge:update", "edge", "{edge_team_directie}"),
        ask("task:create", "task", eenheid_id="{eenheid_team}"),
        ask("node:create", "corpus_node"),
        # a missing resource is no, not a 404
        ask("node:update", "corpus_node", uuid.uuid4()),
        # an existing person is not decided here; creating a contact is
        ask("people:update", "person", "{p_viewer}"),
        ask("people:create", "person"),
    )
    assert got == [True, False, True, True, True, False, False, True]
    missing = ask("edge:delete", "edge", uuid.uuid4())
    assert await evaluate(world, "super_admin", missing) == [False]
    ctx = await perm_ctx(world, "team_editor")
    with pytest.raises(ValueError):
        await can(world.db, ctx, "people:update", "person", world.person["viewer"].id)


_SUBJECT = {"subject": {"type": "user", "id": str(uuid.uuid4())}}
_READ = ask("node:read", "corpus_node")

BAD_BODIES = {
    "empty": {"evaluations": []},
    "too-many": {"evaluations": [_READ] * 51},
    "unknown-type": {"evaluations": [ask("node:read", "onbekend_type")]},
    "bad-type": {"evaluations": [{"action": "node:read", "resource": {"type": "x"}}]},
    "bad-action": {"evaluations": [ask("node read", "corpus_node")]},
    "subject-top": {**_SUBJECT, "evaluations": [_READ]},
    "subject-item": {"evaluations": [{**_READ, **_SUBJECT}]},
}


@pytest.mark.parametrize("name", BAD_BODIES)
async def test_evaluations_reject_bad_input(world, name):
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post("/api/authz/evaluations", json=BAD_BODIES[name])
    assert resp.status_code == 422


def test_evaluations_endpoint_is_not_public():
    from bouwmeester.middleware.auth_required import is_public_path

    assert not is_public_path("/api/authz/evaluations")


# ---------------------------------------------------------------------------
# Grant actions: the core.authority guards
# ---------------------------------------------------------------------------

T, E = "{eenheid_team}", "{eenheid_elders}"
INIT, ND, RO = "{initiatief}", "{node_directie}", "{p_role_only}"
RA, RG, RV = "role:assign", "resource_role:grant", "resource_role:revoke"
OE = "organisatie_eenheid"

# (who, action, resource type, resource id or None, properties, expected)
GRANTS = [
    # role:assign: people:assign_role on the eenheid, lower rank, never yourself
    ("ministry_admin", RA, "role", None, {"role_id": "editor", "eenheid_id": T}, True),
    ("ministry_admin", RA, "role", None, {"role_id": "editor", "eenheid_id": E}, False),
    ("ministry_admin", RA, "role", None,
     {"role_id": "ministry_admin", "eenheid_id": T}, False),
    ("ministry_admin", RA, "role", None,
     {"role_id": "editor", "eenheid_id": T, "target_person_id": "{p_ministry_admin}"},
     False),
    ("manager", RA, "role", None, {"role_id": "editor", "eenheid_id": T}, False),
    ("super_admin", RA, "role", None, {"role_id": "platform_admin"}, True),
    ("ministry_admin", RA, "role", None, {"role_id": "onbekend"}, False),
    # any role to someone else, anywhere or in one eenheid
    ("ministry_admin", RA, "role", None, {"anywhere": True}, True),
    ("ministry_admin", RA, "role", None, {"anywhere": True, "eenheid_id": E}, False),
    ("team_editor", RA, "role", None, {"anywhere": True}, False),
    ("super_admin", RA, "role", None, {"anywhere": True}, True),
    # naming a manager is assigning unit_manager
    ("ministry_admin", "eenheid:set_manager", OE, T, {}, True),
    ("manager", "eenheid:set_manager", OE, T, {}, False),
    # placing an account is the manager's call; editors file a request
    ("manager", "person:place", "person", None, {"eenheid_id": T}, True),
    ("team_editor", "person:place", "person", None, {"eenheid_id": T}, False),
    ("team_editor", "person:place", "person", "{p_viewer}", {"eenheid_id": T}, False),
    # a contact without account: contact administration, people:update
    ("team_editor", "person:place", "person", None,
     {"eenheid_id": T, "contact": True}, True),
    ("platform_admin", "person:place", "person", None,
     {"eenheid_id": T, "contact": True}, False),
    # ending your own placement only gives access up
    ("team_editor", "person:place", "person", "{p_team_editor}",
     {"eenheid_id": T, "ending": True}, True),
    # dissolving an internal eenheid needs its manager
    ("manager", "eenheid:dissolve", OE, T, {}, True),
    ("team_editor", "eenheid:dissolve", OE, T, {}, False),
    # resource roles: resource_permission:manage on the owner, not for
    # yourself, only the type's own rols
    ("manager", RG, "initiatief", INIT, {"rol": "contributor"}, True),
    ("manager", RG, "initiatief", INIT,
     {"rol": "contributor", "target_person_id": "{p_manager}"}, False),
    ("viewer", RG, "initiatief", INIT, {"rol": "viewer"}, False),
    ("afd_editor", RG, "initiatief", INIT, {"rol": "x"}, False),
    # lead contacts: an editor of the lead, opdrachtgever never to yourself
    ("role_only", RG, "lead", "{lead}", {"rol": "opdrachtgever"}, True),
    ("role_only", RG, "lead", "{lead}",
     {"rol": "opdrachtgever", "target_person_id": RO}, False),
    # removing a rol: yourself yes, someone else's only with authority
    ("role_only", RV, "corpus_node", ND,
     {"target_person_id": RO, "rol": "betrokken"}, True),
    ("team_editor", RV, "corpus_node", ND, {"target_person_id": RO}, False),
    ("super_admin", RV, "corpus_node", ND, {"target_person_id": RO}, True),
    ("super_admin", RV, "corpus_node", "{node_team}",  # no such grant
     {"target_person_id": RO}, False),
]  # fmt: skip


@pytest.mark.parametrize(
    ("who", "action", "rtype", "rid", "props", "expected"),
    GRANTS,
    ids=[f"{g[0]}-{g[1]}-{i}" for i, g in enumerate(GRANTS)],
)
async def test_grant_actions_ask_the_authority_guards(
    ew, who, action, rtype, rid, props, expected
):
    assert await evaluate(ew, who, ask(action, rtype, rid, **props)) == [expected]


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
    got = await evaluate(ew, who, ask("role:revoke", "role", assignment_id))
    assert got == [expected]


async def test_the_last_eigenaar_cannot_leave(ew):
    await add(
        ew,
        rp("corpus_node", ew.res["node_free"], "eigenaar", person=ew.person["viewer"]),
    )
    question = ask(
        RV, "corpus_node", "{node_free}", target_person_id="{p_viewer}", rol="eigenaar"
    )
    assert await evaluate(ew, "viewer", question) == [False]


# (who, action, resource type, expected with anywhere=true)
ANYWHERE = [
    ("team_editor", "task:create", "task", True),
    ("manager", "task:create", "task", True),
    ("viewer", "task:create", "task", False),
    ("role_only", "task:create", "task", True),  # a node role granting node:update
    # a contributor creates leads in the initiatief, not without a place
    ("role_only", "lead:create", "lead", False),
    ("platform_admin", "task:create", "task", False),
    ("super_admin", "task:create", "task", True),
    ("team_editor", "lead:create", "lead", True),
    ("viewer", "lead:create", "lead", False),
]  # fmt: skip


@pytest.mark.parametrize(("who", "action", "rtype", "expected"), ANYWHERE)
async def test_anywhere_asks_every_eenheid(ew, who, action, rtype, expected):
    anywhere, nowhere = await evaluate(
        ew, who, ask(action, rtype, anywhere=True), ask(action, rtype)
    )
    assert anywhere is expected
    if rtype == "task" and who != "super_admin":
        assert nowhere is False  # without anywhere a task needs an eenheid


# ---------------------------------------------------------------------------
# Grants to an eenheid, asked like the guards decide them
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["afd_editor", "team_editor", "role_only", "manager"])
async def test_evaluation_grants_to_an_eenheid_like_the_guard(world, who):
    try:
        await authority.require_can_grant_resource_role(
            world.db,
            await perm_ctx(world, who),
            resource_type="initiatief",
            resource_id=world.res["initiatief"],
            rol="contributor",
            target_eenheid_id=world.org["elders"].id,
        )
        expected = True
    except Exception:  # noqa: BLE001 - any refusal is "no"
        expected = False
    question = ask(RG, "initiatief", INIT, rol="contributor", target_eenheid_id=E)
    assert await evaluate(world, who, question) == [expected]


@pytest.mark.parametrize(("who", "expected"), [("afd_editor", True), ("viewer", False)])
async def test_evaluation_revokes_a_grant_of_an_eenheid(iw, who, expected):
    """The owning afdeling manages the grants, a bystander does not."""
    question = ask(RV, "initiatief", INIT, target_eenheid_id="{eenheid_partner}")
    assert await evaluate(iw, who, question) == [expected]


# ---------------------------------------------------------------------------
# GET /api/authz/eenheden equals asking per eenheid
# ---------------------------------------------------------------------------


def _per_eenheid(action: str, eenheid_id, eenheid_type: str | None) -> dict:
    if eenheid_type:
        return ask(action, OE, eenheid_id=eenheid_id, eenheid_type=eenheid_type)
    if action in ("org:update", "org:manage"):
        return ask(action, OE, eenheid_id)
    if action == "org:create":
        return ask(action, OE, eenheid_id=eenheid_id)
    if action == "people:assign_role":
        return ask(RA, "role", anywhere=True, eenheid_id=eenheid_id)
    return ask("person:place", "person", eenheid_id=eenheid_id)


@pytest.mark.parametrize(
    ("action", "eenheid_type"),
    [
        ("org:manage", None),
        ("org:update", None),
        ("org:create", None),
        ("people:assign_role", None),
        ("person:place", None),
        # an internal type needs rights on the parent, an external one not
        ("org:create", "team"),
        ("org:create", "gemeente"),
    ],
)
async def test_eenheden_endpoint_equals_the_evaluations(iw, action, eenheid_type):
    # a synced eenheid below the afdeling: read-only for org:update/manage
    synced = OrganisatieEenheid(
        naam="TOOI-team", type="team", parent_id=iw.org["afdeling"].id, bron="tooi"
    )
    await add(iw, synced)
    eenheden = [*(o.id for o in iw.org.values()), synced.id]
    params = {"action": action}
    if eenheid_type:
        params["eenheid_type"] = eenheid_type
    for who, person in iw.person.items():
        async with client_as(iw.db, person) as c:
            listed = await c.get("/api/authz/eenheden", params=params)
        assert listed.status_code == 200, listed.text
        body = listed.json()
        asked = await evaluate(
            iw, who, *(_per_eenheid(action, e, eenheid_type) for e in eenheden)
        )
        got = [body["all"] or str(e) in set(body["ids"]) for e in eenheden]
        assert got == asked, (who, action, eenheid_type)


async def test_eenheden_endpoint_rejects_other_actions(world):
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.get("/api/authz/eenheden", params={"action": "node:update"})
    assert resp.status_code == 422
