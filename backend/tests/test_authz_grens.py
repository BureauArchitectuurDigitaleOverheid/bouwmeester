"""The boundary of the internal organisation (round-5 decisions).

- Only members of an internal eenheid read up the line; a member of an
  external eenheid sees their own eenheid, not what lies above it.
- Creating or moving an eenheid below a parent needs authority on that
  parent; moving also on the one it leaves, and taking an eenheid out of
  the organisation needs a manager there.
- A trusted placement is only changed or reopened by who decides about the
  members of its eenheid.
- The deploy migration confirms placements of accounts, not of contacts.
- Role assignments of an eenheid are listed for who assigns roles there.
- A parliamentary review task goes to the eenheid of a real membership.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select, text

from bouwmeester.core.authz import can, perm_ctx_for
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.services.organogram_scrape import DgInfo, sync_organogram
from tests.authz_world import World, ask, make_node
from tests.factories import client_as, grant_role, make_org, make_person, place


def _owned_by(person: Person, eenheid: OrganisatieEenheid) -> ResourcePermission:
    return ResourcePermission(
        person_id=person.id,
        resource_type="organisatie_eenheid",
        resource_id=eenheid.id,
        rol="eigenaar",
    )


async def _gemeente(world: World) -> tuple[OrganisatieEenheid, Person, uuid.UUID]:
    """An external partner at the top, owned by someone else, with a node."""
    gemeente = await make_org(world.db, "Gemeente", "gemeente")
    owner = await make_person(world.db, "Gemeentesecretaris")
    world.db.add(_owned_by(owner, gemeente))
    node = await make_node(world.db, "Gemeentedossier", gemeente)
    return gemeente, owner, node.id


async def _sees_node(world: World, person: Person, node_id) -> bool:
    ctx = await perm_ctx_for(world.db, person.id)
    return await can(world.db, ctx, "node:read", "corpus_node", node_id)


# ---------------------------------------------------------------------------
# 1. Read up the line only inside the organisation
# ---------------------------------------------------------------------------


async def test_member_of_external_eenheid_inside_does_not_read_up(world: World):
    stichting = await make_org(world.db, "Stichting", "stichting", world.org["team"])
    own_node = await make_node(world.db, "Stichtingsdossier", stichting)
    partner = await make_person(world.db, "Partner")
    await place(world.db, partner, stichting)

    assert await _sees_node(world, partner, own_node.id)
    for key in ("node_team", "node_afdeling", "node_directie"):
        assert not await _sees_node(world, partner, world.res[key]), key
    async with client_as(world.db, partner) as c:
        detail = await c.get(f"/api/nodes/{world.res['node_team']}")
        initiatief = await c.get(f"/api/initiatieven/{world.res['initiatief']}")
    assert detail.status_code == 404, detail.text
    assert initiatief.status_code == 404, initiatief.text


async def test_member_of_external_child_does_not_read_its_parent(world: World):
    gemeente, _, node_id = await _gemeente(world)
    wijkteam = await make_org(world.db, "Wijkteam", "gemeente", gemeente)
    member = await make_person(world.db, "Wijkteamlid")
    await place(world.db, member, wijkteam)

    assert not await _sees_node(world, member, node_id)


async def test_member_of_internal_eenheid_still_reads_up(world: World):
    viewer = world.person["viewer"]
    assert await _sees_node(world, viewer, world.res["node_directie"])


# ---------------------------------------------------------------------------
# 2. Creating and moving below a parent needs authority on it (H1, H2)
# ---------------------------------------------------------------------------


async def test_nobody_hangs_an_eenheid_below_someone_elses_partner(world: World):
    """H1 (create): an accomplice placed below the partner sees nothing of it."""
    gemeente, _, node_id = await _gemeente(world)
    attacker = world.person["team_editor"]
    async with client_as(world.db, attacker) as c:
        created = await c.post(
            "/api/organisatie",
            json={
                "naam": "Vriendjes",
                "type": "stichting",
                "parent_id": str(gemeente.id),
            },
        )
    assert created.status_code == 403, created.text

    # Even when such an eenheid exists, its members do not read up.
    below = await make_org(world.db, "Vriendjes", "stichting", gemeente)
    accomplice = await make_person(world.db, "Handlanger")
    await place(world.db, accomplice, below)
    async with client_as(world.db, accomplice) as c:
        resp = await c.get(f"/api/nodes/{node_id}")
    assert resp.status_code == 404, resp.text


async def test_nobody_moves_an_eenheid_below_someone_elses_partner(world: World):
    """H1 (move): own stichting, own trusted member, then under the partner."""
    gemeente, _, node_id = await _gemeente(world)
    attacker = world.person["team_editor"]
    accomplice = await make_person(world.db, "Handlanger")
    async with client_as(world.db, attacker) as c:
        created = await c.post(
            "/api/organisatie", json={"naam": "Vriendjes", "type": "stichting"}
        )
        assert created.status_code == 201, created.text
        stichting_id = created.json()["id"]
        placed = await c.post(
            f"/api/people/{accomplice.id}/organisaties",
            json={
                "organisatie_eenheid_id": stichting_id,
                "start_datum": str(date.today()),
            },
        )
        assert placed.status_code == 201, placed.text
        moved = await c.put(
            f"/api/organisatie/{stichting_id}", json={"parent_id": str(gemeente.id)}
        )
    assert moved.status_code == 403, moved.text
    async with client_as(world.db, accomplice) as c:
        resp = await c.get(f"/api/nodes/{node_id}")
    assert resp.status_code == 404, resp.text


async def test_owner_of_partner_creates_and_keeps_its_children(world: World):
    """Below an own partner: allowed, and the child is maintained through it."""
    gemeente, owner, _ = await _gemeente(world)
    async with client_as(world.db, owner) as c:
        created = await c.post(
            "/api/organisatie",
            json={
                "naam": "Wijkteam",
                "type": "gemeente",
                "parent_id": str(gemeente.id),
            },
        )
        assert created.status_code == 201, created.text
        child_id = created.json()["id"]
        renamed = await c.put(f"/api/organisatie/{child_id}", json={"naam": "Wijk"})
    assert renamed.status_code == 200, renamed.text
    # Only a new root gets its own eigenaar.
    grant = await world.db.scalar(
        select(ResourcePermission.id).where(
            ResourcePermission.resource_type == "organisatie_eenheid",
            ResourcePermission.resource_id == uuid.UUID(child_id),
        )
    )
    assert grant is None


async def test_creator_of_child_below_own_team_is_no_eigenaar(world: World):
    async with client_as(world.db, world.person["team_editor"]) as c:
        created = await c.post(
            "/api/organisatie",
            json={
                "naam": "Partner",
                "type": "stichting",
                "parent_id": str(world.org["team"].id),
            },
        )
    assert created.status_code == 201, created.text
    grant = await world.db.scalar(
        select(ResourcePermission.id).where(
            ResourcePermission.resource_type == "organisatie_eenheid",
            ResourcePermission.resource_id == uuid.UUID(created.json()["id"]),
        )
    )
    assert grant is None


async def test_owner_cannot_take_a_partner_out_of_the_organisation(world: World):
    """H2: leaving the organisation needs a manager of the team it leaves."""
    stichting = await make_org(world.db, "Partner", "stichting", world.org["team"])
    world.db.add(_owned_by(world.person["team_editor"], stichting))
    await world.db.flush()
    url = f"/api/organisatie/{stichting.id}"
    async with client_as(world.db, world.person["team_editor"]) as c:
        refused = await c.put(url, json={"parent_id": None})
    assert refused.status_code == 403, refused.text
    async with client_as(world.db, world.person["manager"]) as c:
        allowed = await c.put(url, json={"parent_id": None})
    assert allowed.status_code == 200, allowed.text


async def test_moving_needs_authority_on_the_old_parent(world: World):
    """An owner of the new parent cannot pull someone else's child over."""
    gemeente, owner, _ = await _gemeente(world)
    other, _, _ = await _gemeente(world)
    child = await make_org(world.db, "Wijkteam", "gemeente", other)
    world.db.add(_owned_by(owner, child))
    # org:create somewhere: outside the organisation that used to suffice.
    await grant_role(world.db, owner, "editor", world.org["elders"])
    async with client_as(world.db, owner) as c:
        resp = await c.put(
            f"/api/organisatie/{child.id}", json={"parent_id": str(gemeente.id)}
        )
    assert resp.status_code == 403, resp.text


async def test_create_list_and_evaluation_agree_below_a_parent(world: World):
    gemeente, _, _ = await _gemeente(world)
    own = await make_org(world.db, "Eigen stichting", "stichting")
    editor = world.person["team_editor"]
    world.db.add(_owned_by(editor, own))
    await world.db.flush()
    parents = [world.org["team"], world.org["directie"], gemeente, own]
    async with client_as(world.db, editor) as c:
        listed = (
            await c.get(
                "/api/authz/eenheden",
                params={"action": "org:create", "eenheid_type": "stichting"},
            )
        ).json()
        evaluations = [
            ask(
                "org:create",
                "organisatie_eenheid",
                eenheid_type="stichting",
                eenheid_id=p.id,
            )
            for p in parents
        ]
        decisions = (
            await c.post("/api/authz/evaluations", json={"evaluations": evaluations})
        ).json()["evaluations"]
    got = {p.naam: str(p.id) in listed["ids"] for p in parents}
    assert got == {p.naam: d["decision"] for p, d in zip(parents, decisions)}
    assert got == {
        "Team": True,
        "Directie": False,
        "Gemeente": False,
        "Eigen stichting": True,
    }


# ---------------------------------------------------------------------------
# 3. Trusted placements change only with authority (M1)
# ---------------------------------------------------------------------------


async def _ended(world: World, person: Person, org, bron: str):
    placement = await place(world.db, person, org, bron=bron)
    placement.eind_datum = date.today() - timedelta(days=7)
    await world.db.flush()
    return placement


async def test_reopening_a_sync_placement_needs_authority(world: World):
    kamerlid = await make_person(world.db, "Kamerlid", account=False)
    placement = await _ended(world, kamerlid, world.org["team"], "tk_odata")
    url = f"/api/people/{kamerlid.id}/organisaties/{placement.id}"
    async with client_as(world.db, world.person["viewer"]) as c:
        refused = await c.put(url, json={"eind_datum": None})
        changed = await c.put(url, json={"dienstverband": "extern"})
    assert refused.status_code == 403, refused.text
    assert changed.status_code == 403, changed.text
    async with client_as(world.db, world.person["manager"]) as c:
        allowed = await c.put(url, json={"eind_datum": None})
    assert allowed.status_code == 200, allowed.text
    await world.db.refresh(placement)
    assert placement.bron == "tk_odata" and placement.eind_datum is None


async def test_reopened_manager_placement_is_no_longer_trusted(world: World):
    contact = await make_person(world.db, "Oud-collega", account=False)
    placement = await _ended(world, contact, world.org["team"], "leidinggevende")
    later = date.today() + timedelta(days=30)
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.put(
            f"/api/people/{contact.id}/organisaties/{placement.id}",
            json={"eind_datum": str(later)},
        )
    assert resp.status_code == 200, resp.text
    await world.db.refresh(placement)
    assert placement.bron == "handmatig"


async def test_identity_guard_counts_ended_trusted_placements(world: World):
    contact = await make_person(world.db, "Oud-collega", account=False)
    await _ended(world, contact, world.org["team"], "leidinggevende")
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.post(
            f"/api/people/{contact.id}/emails",
            json={"email": f"kaper-{uuid.uuid4().hex[:6]}@example.com"},
        )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 4. The deploy migration confirms accounts only (M3)
# ---------------------------------------------------------------------------


def _migration(name: str):
    import importlib.util
    from pathlib import Path

    import bouwmeester.migrations

    versions = Path(bouwmeester.migrations.__file__).parent / "versions"
    spec = importlib.util.spec_from_file_location(name, versions / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_migration_confirms_accounts_not_contacts(world: World):
    team = world.org["team"]
    account = await make_person(world.db, "Collega")
    contact = await make_person(world.db, "Contact", account=False)
    role_holder = await make_person(world.db, "Rolhouder", account=False)
    await grant_role(world.db, role_holder, "editor", team)
    agent = await make_person(world.db, "Agent", account=False)
    agent.is_agent = True
    for person in (account, contact, role_holder, agent):
        await place(world.db, person, team, bron="handmatig")

    migration = _migration("7c1e5a9d3b20_confirm_existing_placements")
    await world.db.execute(text(migration.CONFIRM_SQL))

    async def bron(person: Person) -> str:
        return await world.db.scalar(
            select(PersonOrganisatieEenheid.bron).where(
                PersonOrganisatieEenheid.person_id == person.id
            )
        )

    assert await bron(account) == "leidinggevende"
    assert await bron(role_holder) == "leidinggevende"
    assert await bron(agent) == "leidinggevende"
    assert await bron(contact) == "handmatig"


# ---------------------------------------------------------------------------
# 5. Role assignments of an eenheid (L3)
# ---------------------------------------------------------------------------


async def test_eenheid_role_list_is_scoped_to_the_eenheid(world: World):
    admin = await make_person(world.db, "Teambeheerder")
    await grant_role(world.db, admin, "ministry_admin", world.org["team"])
    async with client_as(world.db, admin) as c:
        own = await c.get(f"/api/roles/eenheid/{world.org['team'].id}/assignments")
        other = await c.get(f"/api/roles/eenheid/{world.org['elders'].id}/assignments")
    assert own.status_code == 200, own.text
    assert other.status_code == 403, other.text


# ---------------------------------------------------------------------------
# 6. Parliamentary review unit (L5)
# ---------------------------------------------------------------------------


async def test_review_unit_follows_membership(world: World):
    from bouwmeester.services.parlementair_import_service import (
        ParlementairImportService,
    )

    node = await make_node(world.db, "Dossier", world.org["team"])
    owner = await make_person(world.db, "Eigenaar")
    world.db.add(
        ResourcePermission(
            person_id=owner.id,
            resource_type="corpus_node",
            resource_id=node.id,
            rol="eigenaar",
        )
    )
    await place(world.db, owner, world.org["team"])
    # Informational and ended placements are no membership, however many.
    others = [await make_person(world.db, f"Mede-eigenaar {i}") for i in range(2)]
    for other in others:
        world.db.add(
            ResourcePermission(
                person_id=other.id,
                resource_type="corpus_node",
                resource_id=node.id,
                rol="eigenaar",
            )
        )
    await place(world.db, others[0], world.org["elders"], bron="handmatig")
    await place(world.db, others[1], world.org["elders"], bron="handmatig")
    await _ended(world, others[0], world.org["dg"], "leidinggevende")
    await _ended(world, others[1], world.org["dg"], "leidinggevende")

    service = ParlementairImportService(world.db)
    assert await service._determine_review_unit([node]) == world.org["team"].id


async def test_initiatief_visibility_uses_the_same_boundary(world: World):
    """An initiatief owned above an external eenheid is not visible to its member."""
    stichting = await make_org(world.db, "Stichting", "stichting", world.org["team"])
    member = await make_person(world.db, "Partner")
    await place(world.db, member, stichting)
    initiatief = Initiatief(id=uuid.uuid4(), naam=f"Init {uuid.uuid4().hex[:6]}")
    world.db.add(initiatief)
    await world.db.flush()
    world.db.add(
        ResourcePermission(
            organisatie_eenheid_id=world.org["team"].id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol="eigenaar",
        )
    )
    await world.db.flush()
    ctx = await perm_ctx_for(world.db, member.id)
    assert not await can(world.db, ctx, "initiatief:read", "initiatief", initiatief.id)


# ---------------------------------------------------------------------------
# Confirming a placement settles its pending request
# ---------------------------------------------------------------------------


async def _pending_request(world: World, person: Person):
    from bouwmeester.models.org_placement_request import OrgPlacementRequest

    req = OrgPlacementRequest(
        person_id=person.id,
        organisatie_eenheid_id=world.org["team"].id,
        dienstverband="in_dienst",
    )
    world.db.add(req)
    await world.db.flush()
    return req


async def _place_in_team(world: World, who: str, person: Person):
    async with client_as(world.db, world.person[who]) as c:
        return await c.post(
            f"/api/people/{person.id}/organisaties",
            json={
                "organisatie_eenheid_id": str(world.org["team"].id),
                "start_datum": str(date.today()),
            },
        )


async def test_confirming_by_placing_settles_the_pending_request(world: World):
    newcomer = await make_person(world.db, "Nieuwkomer")
    req = await _pending_request(world, newcomer)
    placed = await _place_in_team(world, "manager", newcomer)
    assert placed.status_code == 201, placed.text
    await world.db.refresh(req)
    assert req.status == "approved"
    assert req.decided_by == world.person["manager"].id
    async with client_as(world.db, world.person["manager"]) as c:
        pending = await c.get("/api/org-placements/pending")
    assert str(req.id) not in {r["id"] for r in pending.json()}


async def test_informational_placement_leaves_the_request_pending(world: World):
    contact = await make_person(world.db, "Contact", account=False)
    req = await _pending_request(world, contact)
    placed = await _place_in_team(world, "viewer", contact)
    assert placed.status_code == 201, placed.text
    await world.db.refresh(req)
    assert req.status == "pending"


# ---------------------------------------------------------------------------
# The assignee reads their own task, whatever the tasks module
# ---------------------------------------------------------------------------


async def test_assignee_without_role_reads_own_task(world: World):
    from bouwmeester.models.task import Task

    freelancer = await make_person(world.db, "Zonder rol")
    task = Task(
        title="Voor de freelancer",
        node_id=world.res["node_team"],
        organisatie_eenheid_id=world.org["team"].id,
        assignee_id=freelancer.id,
        status="open",
    )
    world.db.add(task)
    await world.db.flush()

    ctx = await perm_ctx_for(world.db, freelancer.id)
    assert await can(world.db, ctx, "task:read", "task", task.id)
    assert not await can(world.db, ctx, "task:update", "task", task.id)
    assert not await can(world.db, ctx, "task:read", "task", world.res["task_team"])
    async with client_as(world.db, freelancer) as c:
        detail = await c.get(f"/api/tasks/{task.id}")
        other = await c.get(f"/api/tasks/{world.res['task_team']}")
        listed = await c.get("/api/tasks", params={"assignee_id": str(freelancer.id)})
        everything = await c.get("/api/tasks")
    assert detail.status_code == 200, detail.text
    assert other.status_code == 404, other.text
    assert [t["id"] for t in listed.json()] == [str(task.id)]
    assert [t["id"] for t in everything.json()] == [str(task.id)]


# ---------------------------------------------------------------------------
# 4. External members get nothing implicit (round 6, M1)
# ---------------------------------------------------------------------------

_VIEWER_PERMISSIONS = (
    "people:read",
    "people:update",
    "samenwerkingsverband:read",
    "parlementair:read",
)


async def _own_root_with_member(world: World) -> tuple[str, Person]:
    """An editor's own stichting at the top, with a member they confirmed."""
    member = await make_person(world.db, "Stichtingslid")
    async with client_as(world.db, world.person["team_editor"]) as c:
        created = await c.post(
            "/api/organisatie", json={"naam": "Eigen stichting", "type": "stichting"}
        )
        assert created.status_code == 201, created.text
        root_id = created.json()["id"]
        placed = await c.post(
            f"/api/people/{member.id}/organisaties",
            json={"organisatie_eenheid_id": root_id, "start_datum": str(date.today())},
        )
        assert placed.status_code == 201, placed.text
    return root_id, member


async def test_member_of_an_own_external_root_gets_no_implicit_viewer(world: World):
    _, member = await _own_root_with_member(world)
    ctx = await perm_ctx_for(world.db, member.id)
    for perm in _VIEWER_PERMISSIONS:
        assert not ctx.has_permission(perm), perm
    async with client_as(world.db, member) as c:
        people = await c.get("/api/people")
        edit = await c.put(
            f"/api/people/{world.person['viewer'].id}", json={"functie": "x"}
        )
    assert people.status_code == 403, people.text
    assert edit.status_code == 403, edit.text


async def test_member_of_external_eenheid_inside_keeps_implicit_viewer(world: World):
    stichting = await make_org(world.db, "Stichting", "stichting", world.org["team"])
    partner = await make_person(world.db, "Partner")
    await place(world.db, partner, stichting)
    ctx = await perm_ctx_for(world.db, partner.id)
    for perm in _VIEWER_PERMISSIONS:
        assert ctx.has_permission(perm), perm


# ---------------------------------------------------------------------------
# 5. The internal organisation only grows inside itself (round 6, M3)
# ---------------------------------------------------------------------------


async def _create(world: World, who: str, naam: str, type_: str, parent_id=None):
    body = {"naam": naam, "type": type_}
    if parent_id is not None:
        body["parent_id"] = str(parent_id)
    async with client_as(world.db, world.person[who]) as c:
        return await c.post("/api/organisatie", json=body)


async def test_no_ministerie_below_an_own_root(world: World):
    """The attack: an own root, then a ministerie (or a directie) below it."""
    root_id, _ = await _own_root_with_member(world)
    for type_ in ("ministerie", "directie", "team"):
        resp = await _create(world, "team_editor", "Nep", type_, root_id)
        assert resp.status_code == 403, (type_, resp.text)


async def test_no_internal_team_below_a_partner_root(world: World):
    gemeente, owner, _ = await _gemeente(world)
    await grant_role(world.db, owner, "editor", world.org["elders"])
    world.person["gemeente_owner"] = owner
    resp = await _create(world, "gemeente_owner", "Team", "team", gemeente.id)
    assert resp.status_code == 403, resp.text
    external = await _create(world, "gemeente_owner", "Wijk", "gemeente", gemeente.id)
    assert external.status_code == 201, external.text


async def test_ministerie_only_by_super_admin(world: World):
    below = await _create(
        world, "manager", "Ministerie", "ministerie", world.org["directie"].id
    )
    root = await _create(world, "manager", "Ministerie", "ministerie")
    assert below.status_code == 403, below.text
    assert root.status_code == 403, root.text
    allowed = await _create(world, "super_admin", "Ministerie van Tests", "ministerie")
    assert allowed.status_code == 201, allowed.text


async def test_internal_below_internal_still_works(world: World):
    resp = await _create(
        world, "manager", "Nieuw team", "team", world.org["afdeling"].id
    )
    assert resp.status_code == 201, resp.text


async def test_retyping_an_own_root_into_the_organisation_is_refused(world: World):
    root_id, _ = await _own_root_with_member(world)
    async with client_as(world.db, world.person["team_editor"]) as c:
        for type_ in ("ministerie", "directie"):
            resp = await c.put(f"/api/organisatie/{root_id}", json={"type": type_})
            assert resp.status_code == 403, (type_, resp.text)


async def test_a_manager_cannot_retype_an_eenheid_into_a_ministerie(world: World):
    stichting = await make_org(world.db, "Partner", "stichting", world.org["afdeling"])
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.put(
            f"/api/organisatie/{stichting.id}", json={"type": "ministerie"}
        )
        team = await c.put(f"/api/organisatie/{stichting.id}", json={"type": "team"})
    assert resp.status_code == 403, resp.text
    assert team.status_code == 200, team.text


async def test_retyping_a_ministerie_is_super_admins(world: World):
    url = f"/api/organisatie/{world.org['ministerie'].id}"
    await grant_role(
        world.db, world.person["manager"], "ministry_admin", world.org["ministerie"]
    )
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.put(url, json={"type": "stichting"})
    assert resp.status_code == 403, resp.text


async def test_create_list_and_evaluation_agree_for_internal_types(world: World):
    gemeente, _, _ = await _gemeente(world)
    own = await make_org(world.db, "Eigen stichting", "stichting")
    editor = world.person["team_editor"]
    world.db.add(_owned_by(editor, own))
    await world.db.flush()
    parents = [world.org["team"], gemeente, own]
    expected = {
        "team": {"Team": True, "Gemeente": False, "Eigen stichting": False},
        "ministerie": {"Team": False, "Gemeente": False, "Eigen stichting": False},
    }
    async with client_as(world.db, editor) as c:
        for eenheid_type, want in expected.items():
            listed = (
                await c.get(
                    "/api/authz/eenheden",
                    params={"action": "org:create", "eenheid_type": eenheid_type},
                )
            ).json()
            evaluations = [
                ask(
                    "org:create",
                    "organisatie_eenheid",
                    eenheid_type=eenheid_type,
                    eenheid_id=p.id,
                )
                for p in parents
            ]
            decisions = (
                await c.post(
                    "/api/authz/evaluations", json={"evaluations": evaluations}
                )
            ).json()["evaluations"]
            got = {p.naam: str(p.id) in listed["ids"] for p in parents}
            assert got == {p.naam: d["decision"] for p, d in zip(parents, decisions)}
            assert got == want, eenheid_type


async def test_organogram_scrape_ignores_user_ministeries(world: World):
    """Only official top-level ministeries receive (trusted) DGs."""
    root = await make_org(world.db, "Eigen stichting", "stichting")
    naam = "ministerie van Binnenlandse Zaken en Koninkrijksrelaties"
    below_root = await make_org(world.db, naam, "ministerie", root)
    manual_top = await make_org(world.db, naam, "ministerie")

    async def fake_fetch(slug: str):
        return [DgInfo(naam="DG Overname", detail_url="x")], {}

    await sync_organogram(world.db, fetcher=fake_fetch)
    for ministerie in (below_root, manual_top):
        child = await world.db.scalar(
            select(OrganisatieEenheid.id).where(
                OrganisatieEenheid.parent_id == ministerie.id
            )
        )
        assert child is None
