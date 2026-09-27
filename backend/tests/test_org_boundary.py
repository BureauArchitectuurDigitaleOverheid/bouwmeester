"""The boundary of the internal organisation, and who changes its structure.

- Only members of an internal eenheid read up the line; a member of an
  external eenheid (a partner) sees their own eenheid, nothing above it,
  and gets no implicit viewer rights at the top.
- Creating an eenheid below a parent, and moving one, needs authority on
  that parent (and on the one it leaves); the internal organisation only
  grows inside itself, a ministerie is super_admin's.  The route, the
  evaluation and ``GET /api/authz/eenheden`` answer alike.
- Merging, retyping, bringing in, dissolving and deleting do not carry an
  eigenaar's say over members into the organisation.
"""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.core.authz import perm_ctx_for
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole
from tests import authz_world as aw
from tests.authz_world import World, ask, evaluate, request, rp
from tests.factories import client_as, grant_role, make_org, make_person, place


@pytest.fixture
async def ob(world: World) -> World:
    """Gemeenten (one owned, with a wijkteam member; one with an owned child), own
    roots of the team editor and the manager, a partner inside the team, a
    stichting inside the DG, another ministry's DG, an empty team with a role."""
    db, org, res = world.db, world.org, world.res

    async def eenheid(key, naam, type_, parent=None, owner=None, member=None):
        e = await make_org(db, naam, type_, res[parent] if parent in res else parent)
        res[key] = e
        if owner:
            db.add(rp("organisatie_eenheid", e.id, "eigenaar",
                      person=world.person[owner]))  # fmt: skip
        if member:
            world.person[member] = await make_person(db, member)
            await place(db, world.person[member], e)
        return e

    owner = world.person["gemeente_owner"] = await make_person(db, "Gemeentebaas")
    await grant_role(db, owner, "editor", org["elders"])  # org:create somewhere
    await eenheid("gemeente", "Gemeente", "gemeente", owner="gemeente_owner")
    await eenheid("wijk", "Wijkteam", "gemeente", "gemeente", member="wijk_member")
    await eenheid("other", "Andere gemeente", "gemeente")
    await eenheid("other_child", "Wijk", "gemeente", "other", owner="gemeente_owner")
    await eenheid("own_root", "Eigen stichting", "stichting", None, "team_editor",
                  member="root_member")  # fmt: skip
    await eenheid("partner", "Partner", "stichting", org["team"], "team_editor",
                  member="partner_member")  # fmt: skip
    await eenheid("manager_root", "Stichting directeur", "stichting", owner="manager")
    await eenheid("inside_dg", "Stichting DG", "stichting", org["dg"], "team_editor")
    foreign = await make_org(db, "Ander ministerie", "ministerie")
    await eenheid("foreign_dg", "Ander DG", "directoraat_generaal", foreign)
    await eenheid("empty", "Leeg team", "team", org["afdeling"])
    await grant_role(db, world.person["viewer"], "editor", res["empty"])
    for key in ("gemeente", "partner", "own_root"):
        res[f"{key}_node"] = (await aw.make_node(db, f"Dossier {key}", res[key])).id
    for key, eenheid_key in (("team_admin", "team"), ("min_admin", "ministerie")):
        world.person[key] = await make_person(db, key)
        await grant_role(db, world.person[key], "ministry_admin", org[eenheid_key])
    await db.flush()
    for key, value in list(res.items()):
        if isinstance(value, OrganisatieEenheid):
            res[key] = value.id
    return world


_ORG = "/api/organisatie/{%s}"
_DISSOLVE = {"geldig_tot": "2026-09-27"}

ROUTES = [
    # reading up the line: only from an internal eenheid
    ("partner_member", "GET", "/api/nodes/{partner_node}", None, 200),
    ("partner_member", "GET", "/api/nodes/{node_team}", None, 404),
    ("partner_member", "GET", "/api/nodes/{node_directie}", None, 404),
    ("partner_member", "GET", "/api/initiatieven/{initiatief}", None, 404),
    ("wijk_member", "GET", "/api/nodes/{gemeente_node}", None, 404),
    ("root_member", "GET", "/api/nodes/{own_root_node}", None, 200),
    ("root_member", "GET", "/api/nodes/{node_team}", None, 404),
    ("viewer", "GET", "/api/nodes/{node_directie}", None, 200),
    # a member of an external root reads themselves, not the people directory
    ("partner_member", "GET", "/api/people", None, 200),
    ("root_member", "GET", "/api/people", None, 403),
    ("root_member", "GET", "/api/people/{p_viewer}", None, 403),
    ("root_member", "PUT", "/api/people/{p_viewer}", {"functie": "x"}, 403),
    ("root_member", "GET", "/api/people/{p_root_member}", None, 200),
    ("root_member", "GET", "/api/people/{p_root_member}/organisaties", None, 200),
    # role assignments are listed for who assigns roles there
    ("team_admin", "GET", "/api/roles/eenheid/{eenheid_team}/assignments", None, 200),
    ("team_admin", "GET", "/api/roles/eenheid/{eenheid_elders}/assignments", None, 403),
    # retyping into the organisation, or a ministerie, is super_admin's
    ("team_editor", "PUT", _ORG % "own_root", {"type": "ministerie"}, 403),
    ("team_editor", "PUT", _ORG % "own_root", {"type": "directie"}, 403),
    ("manager", "PUT", _ORG % "partner", {"type": "ministerie"}, 403),
    ("min_admin", "PUT", _ORG % "eenheid_ministerie", {"type": "stichting"}, 403),
    # external with internal eenheden below
    ("manager", "PUT", _ORG % "eenheid_afdeling", {"type": "stichting"}, 403),
    ("super_admin", "PUT", _ORG % "eenheid_afdeling", {"type": "stichting"}, 200),
    # dissolving with members needs the say over them; active roles block a delete
    ("team_editor", "PUT", _ORG % "partner", _DISSOLVE, 403),
    ("manager", "DELETE", _ORG % "empty", None, 409),
]  # fmt: skip


@pytest.mark.parametrize("case", ROUTES, ids=[aw.route_case_id(c) for c in ROUTES])
async def test_routes(ob, case):
    await aw.assert_route_case(ob, *case)


async def test_external_members_get_no_implicit_viewer_at_the_top(ob):
    """Inside the organisation a partner member keeps the implicit viewer."""
    for who, expected in (("root_member", False), ("partner_member", True)):
        ctx = await perm_ctx_for(ob.db, ob.person[who].id)
        for perm in ("people:read", "people:update", "samenwerkingsverband:read",
                     "parlementair:read"):  # fmt: skip
            assert ctx.has_permission(perm) is expected, (who, perm)


# (who, type, parent key or None for the top, may create there)
CREATES = [
    ("team_editor", "gemeente", "eenheid_elders", False),
    ("team_editor", "gemeente", "eenheid_team", True),
    ("viewer", "gemeente", "eenheid_elders", False),
    ("team_editor", "team", "eenheid_elders", False),
    ("team_editor", "team", "eenheid_team", True),
    ("afd_editor", "team", "eenheid_team", True),
    ("team_editor", "stichting", "eenheid_team", True),
    ("team_editor", "stichting", "eenheid_directie", False),
    ("team_editor", "stichting", "own_root", True),
    ("team_editor", "stichting", "gemeente", False),  # someone else's partner
    ("gemeente_owner", "gemeente", "gemeente", True),  # below an own partner
    ("gemeente_owner", "team", "gemeente", False),  # internal below a partner
    ("team_editor", "ministerie", "own_root", False),
    ("team_editor", "directie", "own_root", False),
    ("team_editor", "team", "own_root", False),
    ("team_editor", "team", "gemeente", False),
    ("team_editor", "ministerie", "eenheid_team", False),
    ("manager", "ministerie", "eenheid_directie", False),
    ("manager", "ministerie", None, False),
    ("super_admin", "ministerie", None, True),
    ("manager", "team", "eenheid_afdeling", True),
    ("manager", "stichting", None, True),
    ("manager", "stichting", "manager_root", True),
    ("manager", "gemeente", "eenheid_directie", True),
    ("manager", "gemeente", "eenheid_team", True),
    ("manager", "gemeente", "eenheid_dg", False),
    ("manager", "gemeente", "gemeente", False),
    ("manager", "gemeente", "foreign_dg", False),  # another ministry
]  # fmt: skip


@pytest.mark.parametrize(("who", "type_", "parent", "expected"), CREATES)
async def test_create_route_evaluation_and_list_agree(ob, who, type_, parent, expected):
    body = {"naam": f"Nieuw {uuid.uuid4().hex[:6]}", "type": type_}
    if parent:
        parent_id = ob.values()[parent]
        body["parent_id"] = parent_id
        question = ask("org:create", "organisatie_eenheid", eenheid_id=parent_id,
                       eenheid_type=type_)  # fmt: skip
        assert await evaluate(ob, who, question) == [expected]
        params = {"action": "org:create", "eenheid_type": type_}
        resp = await request(ob, who, "GET", "/api/authz/eenheden", params=params)
        listed = resp.json()
        assert (listed["all"] or parent_id in listed["ids"]) is expected
    resp = await request(ob, who, "POST", "/api/organisatie", body)
    assert resp.status_code == (201 if expected else 403), resp.text


# (who, eenheid key, new parent key or None for the top, may move)
MOVES = [
    ("team_editor", "own_root", "eenheid_team", False),  # bringing it in: a manager
    ("team_editor", "own_root", "gemeente", False),  # below someone else's root
    ("team_editor", "partner", None, False),  # taking it out: a manager there
    ("manager", "partner", None, True),
    ("gemeente_owner", "other_child", "gemeente", False),  # the old parent decides
    ("manager", "manager_root", "foreign_dg", False),
    ("manager", "manager_root", "gemeente", False),
    ("manager", "manager_root", "eenheid_directie", True),
    ("team_editor", "inside_dg", "gemeente", False),
]  # fmt: skip


@pytest.mark.parametrize(("who", "key", "parent", "expected"), MOVES)
async def test_move_route_and_evaluation_agree(ob, who, key, parent, expected):
    parent_id = ob.values()[parent] if parent else None
    resource = {"type": "organisatie_eenheid", "id": str(ob.res[key]),
                "properties": {"parent_id": parent_id}}  # fmt: skip
    question = {"action": "eenheid:move", "resource": resource}
    assert await evaluate(ob, who, question) == [expected]
    eenheid = await ob.db.get(OrganisatieEenheid, ob.res[key])
    before = eenheid.parent_id
    resp = await request(ob, who, "PUT", _ORG % key, {"parent_id": parent_id})
    assert resp.status_code == (200 if expected else 403), resp.text
    await ob.db.refresh(eenheid)
    assert str(eenheid.parent_id) == str(parent_id if expected else before)


# Who holds a say over the members after a change
async def _all(w: World, column, *where) -> list:
    return list((await w.db.scalars(select(column).where(*where))).all())


async def _owner_grants(w: World, eenheid_id) -> list:
    rp_ = ResourcePermission
    return await _all(w, rp_.id, rp_.resource_type == "organisatie_eenheid",
                      rp_.resource_id == eenheid_id, rp_.rol == "eigenaar")  # fmt: skip


async def _open_bronnen(w: World, who: str) -> list[str]:
    poe = PersonOrganisatieEenheid
    return await _all(w, poe.bron, poe.person_id == w.person[who].id,
                      poe.eind_datum.is_(None))  # fmt: skip


async def _pending(w: World, who: str) -> set:
    opr = OrgPlacementRequest
    return set(await _all(w, opr.organisatie_eenheid_id, opr.status == "pending",
                          opr.person_id == w.person[who].id))  # fmt: skip


@pytest.mark.parametrize(
    ("who", "type_", "parent", "rename"),
    [("gemeente_owner", "gemeente", "gemeente", 200),
     ("team_editor", "stichting", "eenheid_team", None)],
)  # fmt: skip
async def test_only_a_new_root_gets_an_eigenaar(ob, who, type_, parent, rename):
    """A child is maintained through its parent, not through its own grant."""
    body = {"naam": "Kind", "type": type_, "parent_id": ob.values()[parent]}
    created = await request(ob, who, "POST", "/api/organisatie", body)
    assert created.status_code == 201, created.text
    ob.res["child"] = child = uuid.UUID(created.json()["id"])
    assert await _owner_grants(ob, child) == []
    if rename:
        renamed = await request(ob, who, "PUT", _ORG % "child", {"naam": "K"})
        assert renamed.status_code == rename, renamed.text


async def test_merging_an_own_root_drops_its_eigenaar_and_unconfirms(ob):
    official = await make_org(ob.db, "Gemeente Officieel", "gemeente")
    official.bron = "tooi"
    ob.person["official"] = await make_person(ob.db, "Ambtenaar")
    await place(ob.db, ob.person["official"], official, bron="abd_scrape")
    body = {"source_id": str(ob.res["own_root"]), "target_id": str(official.id)}
    url = "/api/admin/reconciliation/manual-merge"
    resp = await request(ob, "super_admin", "POST", url, body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["eigenaarsrechten_verwijderd"] == 1
    assert resp.json()["plaatsingen_onbevestigd"] == 1
    assert await _owner_grants(ob, official.id) == []
    assert await _open_bronnen(ob, "root_member") == []
    assert await _pending(ob, "root_member") == {official.id}
    assert await _open_bronnen(ob, "official") == ["abd_scrape"]


async def test_merging_two_teams_changes_nobodys_say(world):
    from bouwmeester.services.merge_organisatie_eenheden import merge_into

    source = await make_org(world.db, "Team oud", "team", world.org["afdeling"])
    world.person["oud"] = await make_person(world.db, "Teamlid oud")
    await place(world.db, world.person["oud"], source)
    result = await merge_into(world.db, source=source, target=world.org["team"])
    assert result.placements_unconfirmed == 0
    assert await _open_bronnen(world, "oud") == ["leidinggevende"]


@pytest.mark.parametrize(("target", "dropped"), [("team", True), ("gemeente", False)])
async def test_merging_into_the_organisation_drops_eigenaars_below(ob, target, dropped):
    """Merged into the organisation, the source's subtree comes in with it:
    an eigenaar grant below the source ends too.  Elsewhere it stays."""
    from bouwmeester.services.merge_organisatie_eenheden import merge_into

    source = await ob.db.get(OrganisatieEenheid, ob.res["other"])
    into = await ob.db.get(OrganisatieEenheid, ob.id(target))
    result = await merge_into(ob.db, source=source, target=into)
    assert result.owner_grants_removed == (1 if dropped else 0)
    assert (await _owner_grants(ob, ob.res["other_child"]) == []) is dropped


async def test_bringing_a_root_in_turns_its_placements_into_requests(ob):
    ob.person["m_member"] = await make_person(ob.db, "Stichtingslid")
    await place(ob.db, ob.person["m_member"], await ob.db.get(
        OrganisatieEenheid, ob.res["manager_root"]))  # fmt: skip
    body = {"parent_id": str(ob.org["team"].id)}
    resp = await request(ob, "manager", "PUT", _ORG % "manager_root", body)
    assert resp.status_code == 200, resp.text
    assert await _owner_grants(ob, ob.res["manager_root"]) == []
    assert await _open_bronnen(ob, "m_member") == []
    assert await _pending(ob, "m_member") == {ob.res["manager_root"]}


async def test_retyping_a_partner_internal_ends_the_eigenaar_grant(ob):
    """It already touched the organisation: its managers confirmed it."""
    resp = await request(ob, "manager", "PUT", _ORG % "partner", {"type": "team"})
    assert resp.status_code == 200, resp.text
    assert await _owner_grants(ob, ob.res["partner"]) == []
    assert await _open_bronnen(ob, "partner_member") == ["leidinggevende"]


async def test_dissolving_ends_every_role_and_placement(world):
    team = world.org["team"]
    resp = await request(world, "manager", "PUT", f"/api/organisatie/{team.id}",
                         _DISSOLVE)  # fmt: skip
    assert resp.status_code == 200, resp.text
    [ended] = await _all(world, PersonRole.eind_datum,
                         PersonRole.person_id == world.person["team_editor"].id,
                         PersonRole.organisatie_eenheid_id == team.id)  # fmt: skip
    assert ended is not None
    assert await _open_bronnen(world, "viewer") == []


async def test_deleting_an_eenheid_is_decided_like_dissolving_it(world):
    """The aanmaker is eigenaar (org:update) but manages no internal eenheid."""
    ids = []
    for body in ({"naam": "Subteam", "type": "team", "parent_id": "{eenheid_team}"},
                 {"naam": "Gemeente X", "type": "gemeente"}):  # fmt: skip
        created = await request(world, "team_editor", "POST", "/api/organisatie", body)
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])
    questions = (ask("eenheid:dissolve", "organisatie_eenheid", i) for i in ids)
    assert await evaluate(world, "team_editor", *questions) == [False, True]
    for i, status in zip(ids, (403, 204)):
        resp = await request(world, "team_editor", "DELETE", f"/api/organisatie/{i}")
        assert resp.status_code == status, resp.text


async def test_staff_directory_is_minimal_without_people_read(ob):
    team, afdeling = ob.org["team"].id, ob.org["afdeling"].id
    async with client_as(ob.db, ob.person["root_member"]) as c:
        flat = (await c.get(f"/api/organisatie/{team}/personen")).json()
        url = f"/api/organisatie/{afdeling}/personen?recursive=true"
        tree = (await c.get(url)).json()
        directie = (await c.get(f"/api/organisatie/{ob.org['directie'].id}")).json()
    async with client_as(ob.db, ob.person["viewer"]) as c:
        full = (await c.get(f"/api/organisatie/{team}/personen")).json()
    assert {p["naam"] for p in flat} >= {"Teamredacteur", "Teamlid"}
    assert all(p["email"] is None and p["emails"] == [] for p in flat)
    assert all(p["last_seen_at"] is None and not p["is_admin"] for p in flat)
    group = next(g for g in tree["children"] if g["eenheid"]["id"] == str(team))
    assert all(p["email"] is None for p in group["personen"])
    assert directie["manager"]["naam"] == "Directeur"
    assert directie["manager"]["email"] is None
    assert all(p["email"] for p in full)
