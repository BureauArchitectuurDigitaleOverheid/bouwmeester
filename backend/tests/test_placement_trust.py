"""Only trusted placements give access, and identity follows them.

A placement is trusted (``leidinggevende``, a sync, a detachering) when who
decides about the members of its eenheid made it; anyone else's is contact
administration (``handmatig``) and becomes a request at first login.  Who
already holds access through a record decides about its email addresses.
Grants to an eenheid never reach the grantor, not even later.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from bouwmeester.core.auth import get_or_create_person
from bouwmeester.core.authority import require_can_grant_resource_role
from bouwmeester.core.authz import can, perm_ctx_for
from bouwmeester.core.whitelist import _get_person_ids_by_emails
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole
from tests import authz_world as aw
from tests.authz_world import World, add, make_agent, request, rp
from tests.factories import client_as, grant_role, make_org, make_person, place

WEEK_AGO = date.today() - timedelta(days=7)


@pytest.fixture
async def pt(world: World) -> World:
    """A contact, a placed new hire, gemeenten (one with a role on an initiatief,
    one the team editor's partner, a bare one, one in another ministry), a
    directie admin who asked to join elders, an eigenaar grant on node elders."""
    db, res = world.db, world.res
    world.person["contact"] = await make_person(db, "Contact", account=False)
    world.person["new_hire"] = await make_person(db, "Nieuwe collega", account=False)
    await place(db, world.person["new_hire"], world.org["team"])
    ander = await make_org(db, "Ander", "ministerie")
    foreign_dg = await make_org(db, "Ander DG", "directoraat_generaal", ander)
    for key, parent in (("gemeente", None), ("partner", None), ("bare", None),
                        ("foreign_gemeente", foreign_dg)):  # fmt: skip
        res[key] = (await make_org(db, key.title(), "gemeente", parent)).id
    await add(world, rp("organisatie_eenheid", res["partner"], "eigenaar",
                        person=world.person["team_editor"]))  # fmt: skip
    for key in ("gemeente", "partner"):
        init = await add(world, Initiatief(id=uuid.uuid4(), naam=f"Init {key}"))
        db.add(rp("initiatief", init.id, "contributor", eenheid=await _org(world, key)))
        res[f"init_{key}"] = init.id
    admin = await aw.add_directie_admin(world, "org_admin", "Directiebeheerder")
    elders = world.org["elders"].id
    db.add(OrgPlacementRequest(person_id=admin.id, dienstverband="in_dienst",
                               organisatie_eenheid_id=elders))  # fmt: skip
    owner = await make_person(db, "Eigenaar elders")
    grant = rp("corpus_node", res["node_elders"], "eigenaar", person=owner)
    res["elders_grant"] = (await add(world, grant)).id
    editor = PersonRole.person_id == world.person["team_editor"].id
    res["editor_role"] = await db.scalar(select(PersonRole.id).where(editor))
    await db.flush()
    return world


async def _org(w: World, key: str):
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

    return await w.db.get(OrganisatieEenheid, w.values()[key])


async def _first_login(w: World, who: str) -> Person:
    email = await w.db.scalar(
        select(PersonEmail.email).where(PersonEmail.person_id == w.person[who].id)
    )
    return await get_or_create_person(
        w.db, sub=f"login-{uuid.uuid4().hex}", email=email, name="", email_verified=True
    )


async def _placement(w: World, who: str, key: str) -> PersonOrganisatieEenheid | None:
    poe = PersonOrganisatieEenheid
    return await w.db.scalar(select(poe).where(
        poe.person_id == w.person[who].id,
        poe.organisatie_eenheid_id == w.values()[key]))  # fmt: skip


async def _pending(w: World, who: str) -> set:
    opr = OrgPlacementRequest
    stmt = select(opr.organisatie_eenheid_id).where(
        opr.person_id == w.person[who].id, opr.status == "pending")  # fmt: skip
    return {str(i) for i in (await w.db.scalars(stmt)).all()}


def _placing(w: World, key: str) -> dict:
    return {"organisatie_eenheid_id": w.values()[key], "start_datum": str(date.today())}


async def _place(w: World, who: str, person: str, key: str):
    url = f"/api/people/{w.person[person].id}/organisaties"
    return await request(w, who, "POST", url, _placing(w, key))


async def _reads(w: World, who: str, key: str, action: str = "initiatief:read"):
    ctx = await perm_ctx_for(w.db, w.person[who].id)
    return await can(w.db, ctx, action, "initiatief", w.res[f"init_{key}"])


# Placing: who makes a placement trusted
# (placer, person, eenheid, status, bron, reads the eenheid's initiatief after)
PLACEMENTS = [
    ("manager", "manager", "eenheid_team", 403, None, None),  # never yourself
    ("manager", "viewer", "foreign_gemeente", 403, None, None),  # another ministry
    ("manager", "viewer", "gemeente", 201, "detachering", False),  # own staff out
    ("viewer", "contact", "partner", 201, "handmatig", False),  # not the owner's
    ("manager", "contact", "partner", 201, "handmatig", False),
    ("team_editor", "contact", "partner", 201, "leidinggevende", True),  # owner
]  # fmt: skip


@pytest.mark.parametrize(("placer", "person", "key", "status", "bron", "reads"),
                         PLACEMENTS)  # fmt: skip
async def test_who_places_decides_the_trust(pt, placer, person, key, status, bron,
                                            reads):  # fmt: skip
    resp = await _place(pt, placer, person, key)
    assert resp.status_code == status, resp.text
    if status != 201:
        return
    assert (await _placement(pt, person, key)).bron == bron
    if person == "contact":
        await _first_login(pt, "contact")
    assert await _reads(pt, person, key) is reads
    assert await _reads(pt, person, key, "initiatief:update") is reads
    async with client_as(pt.db, pt.person[person]) as c:
        listed = {i["id"] for i in (await c.get("/api/initiatieven")).json()}
    assert (str(pt.res[f"init_{key}"]) in listed) is reads


async def test_a_synced_member_shares_the_partner_grant(pt):
    pt.person["wethouder"] = await make_person(pt.db, "Wethouder")
    await place(pt.db, pt.person["wethouder"], await _org(pt, "gemeente"),
                bron="abd_scrape")  # fmt: skip
    assert await _reads(pt, "wethouder", "gemeente", "initiatief:update")


async def test_a_contact_placement_waits_for_a_manager_at_first_login(pt):
    for key in ("eenheid_team", "gemeente"):
        assert (await _place(pt, "viewer", "contact", key)).status_code == 201
    await _first_login(pt, "contact")
    assert await _placement(pt, "contact", "eenheid_team") is None
    assert await _pending(pt, "contact") == {pt.values()["eenheid_team"]}
    assert await _placement(pt, "contact", "gemeente") is not None
    assert await aw.notifications(pt, pt.person["manager"].id, "placement_request")


async def test_a_manager_confirms_a_contact_placement(pt):
    await place(pt.db, pt.person["contact"], pt.org["team"], bron="handmatig")
    assert (await _place(pt, "viewer", "contact", "eenheid_team")).status_code == 409
    assert (await _place(pt, "manager", "contact", "eenheid_team")).status_code == 201
    assert (await _place(pt, "manager", "contact", "eenheid_team")).status_code == 409
    assert (await _placement(pt, "contact", "eenheid_team")).bron == "leidinggevende"


@pytest.mark.parametrize(("placer", "person", "status"),
                         [("manager", "newcomer", "approved"),
                          ("viewer", "contact", "pending")])  # fmt: skip
async def test_placing_settles_a_pending_request_only_when_trusted(
    pt, placer, person, status
):
    if person == "newcomer":
        pt.person["newcomer"] = await make_person(pt.db, "Nieuwkomer")
    req = await add(pt, OrgPlacementRequest(
        person_id=pt.person[person].id, organisatie_eenheid_id=pt.org["team"].id,
        dienstverband="in_dienst"))  # fmt: skip
    assert (await _place(pt, placer, person, "eenheid_team")).status_code == 201
    await pt.db.refresh(req)
    assert req.status == status
    if status == "approved":
        assert req.decided_by == pt.person["manager"].id
        async with client_as(pt.db, pt.person["manager"]) as c:
            pending = (await c.get("/api/org-placements/pending")).json()
        assert str(req.id) not in {r["id"] for r in pending}


@pytest.mark.parametrize(("who", "status"), [("team_editor", 200), ("manager", 403)])
async def test_the_owner_of_a_partner_decides_its_requests(pt, who, status):
    req = await add(pt, OrgPlacementRequest(
        person_id=pt.person["viewer"].id, organisatie_eenheid_id=pt.res["partner"],
        dienstverband="in_dienst"))  # fmt: skip
    async with client_as(pt.db, pt.person[who]) as c:
        pending = {r["id"] for r in (await c.get("/api/org-placements/pending")).json()}
        resp = await c.post(f"/api/org-placements/{req.id}/approve")
    assert resp.status_code == status, resp.text
    assert (str(req.id) in pending) is (status == 200)
    assert await _reads(pt, "viewer", "partner") is (status == 200)


async def test_an_informational_placement_still_needs_onboarding(world):
    newcomer = await make_person(world.db, "Nieuwkomer")
    world.person["newcomer"] = newcomer
    await place(world.db, newcomer, world.org["team"], bron="handmatig")
    body = {"naam": "Nieuwkomer", "functie": "Beleid",
            "organisatie_eenheid_id": str(world.org["team"].id)}  # fmt: skip
    resp = await request(world, "newcomer", "POST", "/api/auth/onboarding", body)
    assert resp.status_code == 200, resp.text
    assert await _pending(world, "newcomer") == {str(world.org["team"].id)}


# Changing a placement: a trusted one only by who decides, else it is demoted
_LATER = str(date.today() + timedelta(days=30))
_TODAY = str(date.today())

# (bron, ended, actor, method, body, status, bron after)
CHANGES = [
    ("tk_odata", True, "viewer", "PUT", {"eind_datum": None}, 403, "tk_odata"),
    ("tk_odata", True, "viewer", "PUT", {"dienstverband": "extern"}, 403, "tk_odata"),
    ("tk_odata", True, "manager", "PUT", {"eind_datum": None}, 200, "tk_odata"),
    ("leidinggevende", True, "viewer", "PUT", {"eind_datum": _LATER}, 200, "handmatig"),
    ("leidinggevende", False, "viewer", "PUT", {"dienstverband": "ingehuurd"}, 200,
     "handmatig"),
    ("leidinggevende", False, "team_editor", "PUT", {"eind_datum": _TODAY}, 403,
     "leidinggevende"),
    ("leidinggevende", False, "team_editor", "DELETE", None, 403, "leidinggevende"),
    ("leidinggevende", False, "manager", "DELETE", None, 204, None),
    ("handmatig", False, "team_editor", "DELETE", None, 204, None),
]  # fmt: skip


@pytest.mark.parametrize(("bron", "ended", "who", "method", "body", "status", "after"),
                         CHANGES)  # fmt: skip
async def test_changing_a_placement(pt, bron, ended, who, method, body, status, after):
    placement = await place(pt.db, pt.person["contact"], pt.org["team"], bron=bron)
    if ended:
        placement.eind_datum = WEEK_AGO
    await pt.db.flush()
    url = f"/api/people/{pt.person['contact'].id}/organisaties/{placement.id}"
    resp = await request(pt, who, method, url, body)
    assert resp.status_code == status, resp.text
    if after:
        await pt.db.refresh(placement)
        assert placement.bron == after
        if status == 200 and "eind_datum" in body:
            assert str(placement.eind_datum) == str(body["eind_datum"])


async def test_the_deploy_migration_confirms_accounts_not_contacts(pt):
    team = pt.org["team"]
    stichting = await make_org(pt.db, "Stichting", "stichting", team)
    colleague = await make_person(pt.db, "Collega")
    ended = await make_person(pt.db, "Vertrokken")
    role_holder = await make_person(pt.db, "Rolhouder", account=False)
    await grant_role(pt.db, role_holder, "editor", team)
    agent = await make_agent(pt)
    gemeente, contact = await _org(pt, "gemeente"), pt.person["contact"]
    trusted, kept = "leidinggevende", "handmatig"
    rows = [(colleague, team, trusted), (colleague, stichting, trusted),
            (colleague, gemeente, trusted), (role_holder, team, trusted),
            (agent, team, trusted), (contact, team, kept),
            (ended, team, kept)]  # fmt: skip
    placements = [await place(pt.db, p, o, bron="handmatig") for p, o, _ in rows]
    # A week back: the migration compares with the database's CURRENT_DATE (UTC).
    placements[-1].eind_datum = WEEK_AGO
    await pt.db.flush()
    migration = aw.load_migration("7c1e5a9d3b20_confirm_existing_placements")
    await pt.db.execute(text(migration.CONFIRM_SQL))
    for placement, (_, _, bron) in zip(placements, rows):
        await pt.db.refresh(placement)
        assert placement.bron == bron, (placement.person_id, bron)


# Identity: who holds access through a record decides its addresses
async def _target(w: World, setup: str) -> str:
    """The person whose addresses are changed, per setup; returns its key."""
    if setup == "self":
        return "role_only"
    if setup == "agent":
        await make_agent(w, "target")
        return "target"
    target = w.person["target"] = await make_person(w.db, "Doel", account=False)
    if setup in ("leidinggevende", "roo_leidinggevende", "handmatig", "ended"):
        bron = "leidinggevende" if setup == "ended" else setup
        placement = await place(w.db, target, w.org["team"], bron=bron)
        placement.eind_datum = WEEK_AGO if setup == "ended" else None
    elif setup == "task":
        from bouwmeester.models.task import Task

        (await w.db.get(Task, w.res["task_elders"])).assignee_id = target.id
    elif setup in ("reaching", "bare"):
        await place(w.db, target, await _org(w, "gemeente" if setup == "reaching"
                                             else "bare"), bron="tk_odata")  # fmt: skip
    elif setup == "grant":
        w.db.add(rp("corpus_node", w.res["node_directie"], "betrokken", person=target))
    await w.db.flush()
    return "target"


# (setup of the person, who adds an address, status)
EMAILS = [
    ("leidinggevende", "viewer", 403),  # the placement goes with it at login
    ("leidinggevende", "manager", 201),
    ("roo_leidinggevende", "viewer", 403),  # an imported internal placement
    ("ended", "viewer", 403),  # an ended trusted placement counts too
    ("handmatig", "viewer", 201),  # becomes a request: nothing to take over
    ("task", "viewer", 403),  # the assignee reads the task
    ("task", "super_admin", 201),
    ("reaching", "viewer", 403),  # a trusted external placement that reaches
    ("bare", "viewer", 201),
    ("grant", "viewer", 403),
    ("grant", "manager", 201),
    ("agent", "target", 403),  # an agent does not change its own addresses
    ("agent", "super_admin", 201),
    ("self", "role_only", 201),  # your own record needs no people:update
]  # fmt: skip


@pytest.mark.parametrize(("setup", "who", "status"), EMAILS)
async def test_adding_an_email_needs_authority_over_the_access(pt, setup, who, status):
    target = await _target(pt, setup)
    email = f"extra-{uuid.uuid4().hex[:8]}@example.com"
    url = f"/api/people/{pt.person[target].id}/emails"
    resp = await request(pt, who, "POST", url, {"email": email})
    assert resp.status_code == status, resp.text
    if status == 201:
        added = select(PersonEmail.added_by_id).where(PersonEmail.email == email)
        assert await pt.db.scalar(added) == pt.person[who].id


async def test_login_never_links_to_an_agent(world):
    agent = await make_agent(world)
    person = await get_or_create_person(world.db, "sub-agent-login", agent.email,
                                        "Iemand", email_verified=True)  # fmt: skip
    assert person.id != agent.id and not person.is_agent
    await world.db.refresh(agent)
    assert agent.oidc_subject is None


@pytest.mark.parametrize(
    ("added_by", "trusted"), [("viewer", False), ("manager", True)]
)
async def test_login_through_a_pre_seeded_address(pt, added_by, trusted):
    """An address only who confirms the placement added keeps its access."""
    contact = pt.person["contact"]
    alt = f"alt-{uuid.uuid4().hex[:8]}@example.com"
    pt.db.add(PersonEmail(person_id=contact.id, email=alt,
                          added_by_id=pt.person[added_by].id))  # fmt: skip
    await place(pt.db, contact, pt.org["team"])
    await grant_role(pt.db, contact, "editor", pt.org["team"])
    person = await get_or_create_person(pt.db, "sub-alt", alt, "C", email_verified=True)
    assert person.id == contact.id
    placement = await _placement(pt, "contact", "eenheid_team")
    assert (placement is not None and placement.eind_datum is None) is trusted
    assert bool(await _pending(pt, "contact")) is not trusted
    role = await pt.db.scalar(
        select(PersonRole).where(PersonRole.person_id == contact.id)
    )
    assert (role.eind_datum is None) is trusted


async def test_admin_seed_promotes_only_on_a_sole_address(world):
    sole = await make_person(world.db, "Enige", account=False)
    several = await make_person(world.db, "Meerdere", account=False)
    await add(world, PersonEmail(person_id=several.id, email="tweede@example.com"))
    ids = await _get_person_ids_by_emails(world.db, {sole.email, several.email})
    assert ids == {sole.id}


# Grants and roles never reach further than the grantor's own say
ROUTES = [
    ("viewer", "PUT", "/api/people/{p_new_hire}", {"functie": "Nieuw"}, 200),
    # sharing with an eenheid you asked to join is sharing with yourself
    ("org_admin", "POST", "/api/sharing", {"source_eenheid_id": "{eenheid_afdeling}",
     "target_eenheid_id": "{eenheid_elders}", "access_level": "edit"}, 403),
    # giving up your own role needs no people:assign_role, assigning does
    ("team_editor", "DELETE", "/api/roles/assignments/{editor_role}", None, 200),
    ("team_editor", "POST", "/api/roles/assign", {"person_id": "{p_viewer}",
     "role_id": "editor", "organisatie_eenheid_id": "{eenheid_team}"}, 403),
    # the last-owner rule does not answer who cannot see the node
    ("team_editor", "DELETE", "/api/resource-permissions/{elders_grant}", None, 404),
    ("team_editor", "PUT", "/api/resource-permissions/{elders_grant}",
     {"rol": "betrokken"}, 404),
]  # fmt: skip


@pytest.mark.parametrize("case", ROUTES, ids=[aw.route_case_id(c) for c in ROUTES])
async def test_routes(pt, case):
    await aw.assert_route_case(pt, *case)


@pytest.mark.parametrize("link", ["fresh", "requested", "joins_later"])
async def test_an_eenheid_grant_never_reaches_the_grantor(world, link):
    """The afdeling owns the initiatief, so its editor hands out roles."""
    sub = await make_org(world.db, "Nieuw team", "team", world.org["afdeling"])
    editor = world.person["afd_editor"]
    if link == "requested":
        world.db.add(OrgPlacementRequest(person_id=editor.id, dienstverband="in_dienst",
                                         organisatie_eenheid_id=sub.id))  # fmt: skip
    elif link == "joins_later":
        world.db.add(PersonOrganisatieEenheid(
            person_id=editor.id, organisatie_eenheid_id=sub.id, bron="leidinggevende",
            start_datum=date.today() + timedelta(days=7)))  # fmt: skip
    await world.db.flush()

    async def grant():
        await require_can_grant_resource_role(
            world.db, await aw.perm_ctx(world, "afd_editor"),
            resource_type="initiatief",
            resource_id=world.res["initiatief"], rol="contributor",
            target_eenheid_id=sub.id)  # fmt: skip

    if link != "fresh":
        with pytest.raises(HTTPException) as exc:
            await grant()
        assert exc.value.status_code == 403
        return
    await grant()
    world.res["sub"] = sub.id
    body = {"organisatie_eenheid_id": "{sub}", "start_datum": str(date.today())}
    resp = await request(world, "afd_editor", "POST",
                         f"/api/people/{editor.id}/organisaties", body)  # fmt: skip
    assert resp.status_code == 403, resp.text
