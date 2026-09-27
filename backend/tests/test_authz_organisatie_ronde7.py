"""Round 7: organisation, people and identity.

Each test pins one finding of the round-7 audit: merging and moving
eenheden must not carry an eigenaar's say over members into the
organisation, agents and pre-seeded addresses must not take over records,
dissolving and deleting handle every role and placement, trusted
placements are ended only by who decides about the members, and the staff
directory shows only who is where to people without ``people:read``.
"""

import uuid

from sqlalchemy import select

from bouwmeester.core.auth import get_or_create_person
from bouwmeester.core.whitelist import _get_person_ids_by_emails
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import (
    PLACEMENT_BRON_HANDMATIG,
    PersonOrganisatieEenheid,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole
from bouwmeester.services.merge_organisatie_eenheden import merge_into
from tests.authz_world import World
from tests.factories import client_as, grant_role, make_org, make_person, place


def _owned_by(person: Person, eenheid: OrganisatieEenheid) -> ResourcePermission:
    return ResourcePermission(
        person_id=person.id,
        resource_type="organisatie_eenheid",
        resource_id=eenheid.id,
        rol="eigenaar",
    )


async def _owner_grants(w: World, eenheid_id) -> list[ResourcePermission]:
    return list(
        (
            await w.db.scalars(
                select(ResourcePermission).where(
                    ResourcePermission.resource_type == "organisatie_eenheid",
                    ResourcePermission.resource_id == eenheid_id,
                    ResourcePermission.rol == "eigenaar",
                )
            )
        ).all()
    )


async def _open_placements(w: World, person: Person) -> list[PersonOrganisatieEenheid]:
    return list(
        (
            await w.db.scalars(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.person_id == person.id,
                    PersonOrganisatieEenheid.eind_datum.is_(None),
                )
            )
        ).all()
    )


async def _pending(w: World, person: Person) -> set:
    return set(
        (
            await w.db.scalars(
                select(OrgPlacementRequest.organisatie_eenheid_id).where(
                    OrgPlacementRequest.person_id == person.id,
                    OrgPlacementRequest.status == "pending",
                )
            )
        ).all()
    )


async def _own_root_with_member(w: World, owner: Person):
    """An external root *owner* made, with a member *owner* confirmed."""
    root = await make_org(w.db, f"Eigen stichting {uuid.uuid4().hex[:6]}", "stichting")
    w.db.add(_owned_by(owner, root))
    member = await make_person(w.db, "Buitenstaander")
    await place(w.db, member, root)
    return root, member


# ---------------------------------------------------------------------------
# F1: merging an own root into an official eenheid
# ---------------------------------------------------------------------------


async def test_merge_drops_the_eigenaar_and_unconfirms_its_placements(world: World):
    owner = world.person["team_editor"]
    root, member = await _own_root_with_member(world, owner)
    official = await make_org(world.db, "Gemeente Officieel", "gemeente")
    official.bron = "tooi"
    official_member = await make_person(world.db, "Gemeenteambtenaar")
    await place(world.db, official_member, official, bron="abd_scrape")
    await world.db.flush()

    result = await merge_into(world.db, source=root, target=official)

    assert result.owner_grants_removed == 1
    assert result.placements_unconfirmed == 1
    assert await _owner_grants(world, official.id) == []
    assert await _open_placements(world, member) == []
    assert await _pending(world, member) == {official.id}
    # The official row's own members are not touched.
    assert [p.bron for p in await _open_placements(world, official_member)] == [
        "abd_scrape"
    ]


async def test_merge_keeps_placements_its_confirmers_still_decide(world: World):
    """Merging two teams of the same directie changes nobody's say."""
    source = await make_org(world.db, "Team oud", "team", world.org["afdeling"])
    member = await make_person(world.db, "Teamlid oud")
    await place(world.db, member, source)

    result = await merge_into(world.db, source=source, target=world.org["team"])

    assert result.placements_unconfirmed == 0
    [placement] = await _open_placements(world, member)
    assert placement.organisatie_eenheid_id == world.org["team"].id
    assert placement.bron == "leidinggevende"


async def test_manual_merge_reports_what_it_took_away(world: World):
    root, _ = await _own_root_with_member(world, world.person["team_editor"])
    official = await make_org(world.db, "Gemeente Doel", "gemeente")
    async with client_as(world.db, world.person["super_admin"]) as c:
        resp = await c.post(
            "/api/admin/reconciliation/manual-merge",
            json={"source_id": str(root.id), "target_id": str(official.id)},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eigenaarsrechten_verwijderd"] == 1
    assert body["plaatsingen_onbevestigd"] == 1


# ---------------------------------------------------------------------------
# F8: bringing an eenheid into the organisation
# ---------------------------------------------------------------------------


async def test_editor_cannot_bring_an_own_root_into_the_organisation(world: World):
    """The exact attack: own root, trusted outsider, move below own team."""
    editor = world.person["team_editor"]
    async with client_as(world.db, editor) as c:
        created = await c.post(
            "/api/organisatie", json={"naam": "Mijn stichting", "type": "stichting"}
        )
        assert created.status_code == 201, created.text
        root_id = created.json()["id"]
        outsider = await make_person(world.db, "Buitenstaander")
        placed = await c.post(
            f"/api/people/{outsider.id}/organisaties",
            json={"organisatie_eenheid_id": root_id, "start_datum": "2026-01-01"},
        )
        assert placed.status_code == 201, placed.text
        moved = await c.put(
            f"/api/organisatie/{root_id}",
            json={"parent_id": str(world.org["team"].id)},
        )
    assert moved.status_code == 403, moved.text
    root = await world.db.get(OrganisatieEenheid, uuid.UUID(root_id))
    assert root.parent_id is None


async def test_manager_brings_a_root_in_and_its_placements_become_requests(
    world: World,
):
    # The eigenaar of the root is also a manager of the parent it goes to.
    root, member = await _own_root_with_member(world, world.person["manager"])
    await world.db.flush()
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.put(
            f"/api/organisatie/{root.id}",
            json={"parent_id": str(world.org["team"].id)},
        )
    assert resp.status_code == 200, resp.text
    assert await _owner_grants(world, root.id) == []
    assert await _open_placements(world, member) == []
    assert await _pending(world, member) == {root.id}


async def test_retype_to_internal_ends_the_eigenaar_grant(world: World):
    partner = await make_org(world.db, "Partner", "stichting", world.org["team"])
    owner = world.person["team_editor"]
    world.db.add(_owned_by(owner, partner))
    member = await make_person(world.db, "Partnerlid")
    await place(world.db, member, partner)
    await world.db.flush()
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.put(f"/api/organisatie/{partner.id}", json={"type": "team"})
    assert resp.status_code == 200, resp.text
    assert await _owner_grants(world, partner.id) == []
    # It already touched the organisation: its managers confirmed it.
    [placement] = await _open_placements(world, member)
    assert placement.bron == "leidinggevende"


# ---------------------------------------------------------------------------
# F2: retyping to external with internal eenheden below
# ---------------------------------------------------------------------------


async def test_retype_to_external_with_internal_below_is_super_admins(world: World):
    afdeling = world.org["afdeling"]
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.put(
            f"/api/organisatie/{afdeling.id}", json={"type": "stichting"}
        )
    assert resp.status_code == 403, resp.text
    async with client_as(world.db, world.person["super_admin"]) as c:
        resp = await c.put(
            f"/api/organisatie/{afdeling.id}", json={"type": "stichting"}
        )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# F3: agents and identity
# ---------------------------------------------------------------------------


async def _agent(w: World) -> Person:
    agent = await make_person(w.db, "Agent", account=False)
    agent.is_agent = True
    await w.db.flush()
    return agent


async def test_agent_cannot_change_its_own_addresses(world: World):
    agent = await _agent(world)
    async with client_as(world.db, agent) as c:
        resp = await c.post(
            f"/api/people/{agent.id}/emails", json={"email": "overname@example.com"}
        )
    assert resp.status_code == 403, resp.text
    async with client_as(world.db, world.person["super_admin"]) as c:
        resp = await c.post(
            f"/api/people/{agent.id}/emails", json={"email": "beheer@example.com"}
        )
    assert resp.status_code == 201, resp.text


async def test_login_never_links_to_an_agent(world: World):
    agent = await _agent(world)
    person = await get_or_create_person(
        world.db, "sub-agent-login", agent.email, "Iemand", email_verified=True
    )
    assert person.id != agent.id
    assert not person.is_agent
    await world.db.refresh(agent)
    assert agent.oidc_subject is None


# ---------------------------------------------------------------------------
# F6/F5: pre-seeded contact addresses
# ---------------------------------------------------------------------------


async def _placed_contact(w: World, added_by: Person) -> tuple[Person, str]:
    """A contact a manager placed and gave a role, with an address by *added_by*."""
    contact = await make_person(w.db, "Nieuwe collega", account=False)
    alt = f"alt-{uuid.uuid4().hex[:8]}@example.com"
    w.db.add(PersonEmail(person_id=contact.id, email=alt, added_by_id=added_by.id))
    await place(w.db, contact, w.org["team"])
    await grant_role(w.db, contact, "editor", w.org["team"])
    return contact, alt


async def test_login_through_an_address_a_non_confirmer_added_holds_access(
    world: World,
):
    contact, alt = await _placed_contact(world, world.person["viewer"])
    person = await get_or_create_person(
        world.db, "sub-alt", alt, "Nieuwe collega", email_verified=True
    )
    assert person.id == contact.id
    assert await _open_placements(world, contact) == []
    assert await _pending(world, contact) == {world.org["team"].id}
    role = await world.db.scalar(
        select(PersonRole).where(PersonRole.person_id == contact.id)
    )
    assert role.eind_datum is not None


async def test_login_through_an_address_the_manager_added_keeps_access(world: World):
    contact, alt = await _placed_contact(world, world.person["manager"])
    await get_or_create_person(
        world.db, "sub-alt-ok", alt, "Nieuwe collega", email_verified=True
    )
    [placement] = await _open_placements(world, contact)
    assert placement.bron == "leidinggevende"


async def test_adding_an_address_records_who_added_it(world: World):
    contact = await make_person(world.db, "Contact", account=False)
    viewer = world.person["viewer"]
    async with client_as(world.db, viewer) as c:
        resp = await c.post(
            f"/api/people/{contact.id}/emails", json={"email": "extra@example.com"}
        )
    assert resp.status_code == 201, resp.text
    added_by = await world.db.scalar(
        select(PersonEmail.added_by_id).where(PersonEmail.email == "extra@example.com")
    )
    assert added_by == viewer.id


async def test_admin_seed_promotes_a_never_logged_in_person_on_its_sole_address(
    world: World,
):
    sole = await make_person(world.db, "Enige", account=False)
    several = await make_person(world.db, "Meerdere", account=False)
    world.db.add(PersonEmail(person_id=several.id, email="tweede@example.com"))
    await world.db.flush()
    ids = await _get_person_ids_by_emails(world.db, {sole.email, several.email})
    assert ids == {sole.id}


# ---------------------------------------------------------------------------
# F7: deleting and dissolving
# ---------------------------------------------------------------------------


async def test_deleting_an_eenheid_with_active_roles_is_refused(world: World):
    empty = await make_org(world.db, "Leeg team", "team", world.org["afdeling"])
    await grant_role(world.db, world.person["viewer"], "editor", empty)
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.delete(f"/api/organisatie/{empty.id}")
    assert resp.status_code == 409, resp.text
    assert "rollen" in resp.json()["detail"]


async def test_dissolving_ends_every_role_and_placement(world: World):
    team = world.org["team"]
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.put(
            f"/api/organisatie/{team.id}", json={"geldig_tot": "2026-09-27"}
        )
    assert resp.status_code == 200, resp.text
    editor_role = await world.db.scalar(
        select(PersonRole).where(
            PersonRole.person_id == world.person["team_editor"].id,
            PersonRole.organisatie_eenheid_id == team.id,
        )
    )
    assert editor_role.eind_datum is not None
    assert await _open_placements(world, world.person["viewer"]) == []


async def test_dissolving_with_members_needs_the_say_over_them(world: World):
    """Its eigenaar edits it (org:update) but, inside the organisation, does
    not decide about its members: only a manager dissolves it then."""
    partner = await make_org(world.db, "Partnerclub", "stichting", world.org["team"])
    world.db.add(_owned_by(world.person["team_editor"], partner))
    member = await make_person(world.db, "Clublid")
    await place(world.db, member, partner)
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.put(
            f"/api/organisatie/{partner.id}", json={"geldig_tot": "2026-09-27"}
        )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# F4: ending a trusted placement of a contact
# ---------------------------------------------------------------------------


async def test_only_who_confirms_ends_a_contacts_trusted_placement(world: World):
    contact = await make_person(world.db, "Nieuwe medewerker", account=False)
    placement = await place(world.db, contact, world.org["team"])
    url = f"/api/people/{contact.id}/organisaties/{placement.id}"
    async with client_as(world.db, world.person["team_editor"]) as c:
        assert (await c.put(url, json={"eind_datum": "2026-09-27"})).status_code == 403
        assert (await c.delete(url)).status_code == 403
    async with client_as(world.db, world.person["manager"]) as c:
        assert (await c.delete(url)).status_code == 204


async def test_contact_administration_still_ends_informational_placements(
    world: World,
):
    contact = await make_person(world.db, "Contactpersoon", account=False)
    placement = await place(
        world.db, contact, world.org["team"], bron=PLACEMENT_BRON_HANDMATIG
    )
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.delete(f"/api/people/{contact.id}/organisaties/{placement.id}")
    assert resp.status_code == 204, resp.text


# ---------------------------------------------------------------------------
# e2e: the staff directory and reading yourself
# ---------------------------------------------------------------------------


async def _external_member(w: World) -> Person:
    root, member = await _own_root_with_member(w, w.person["team_editor"])
    return member


async def test_staff_directory_is_minimal_without_people_read(world: World):
    outsider = await _external_member(world)
    team = world.org["team"]
    async with client_as(world.db, outsider) as c:
        flat = (await c.get(f"/api/organisatie/{team.id}/personen")).json()
        tree = (
            await c.get(
                f"/api/organisatie/{world.org['afdeling'].id}/personen?recursive=true"
            )
        ).json()
        eenheid = (await c.get(f"/api/organisatie/{world.org['directie'].id}")).json()
    assert {p["naam"] for p in flat} >= {"Teamredacteur", "Teamlid"}
    assert all(p["email"] is None and p["emails"] == [] for p in flat)
    assert all(p["last_seen_at"] is None and not p["is_admin"] for p in flat)
    team_group = next(g for g in tree["children"] if g["eenheid"]["id"] == str(team.id))
    assert all(p["email"] is None for p in team_group["personen"])
    assert eenheid["manager"]["naam"] == "Directeur"
    assert eenheid["manager"]["email"] is None


async def test_staff_directory_is_full_with_people_read(world: World):
    async with client_as(world.db, world.person["viewer"]) as c:
        flat = (await c.get(f"/api/organisatie/{world.org['team'].id}/personen")).json()
    assert all(p["email"] for p in flat)


async def test_external_member_reads_themselves_not_others(world: World):
    outsider = await _external_member(world)
    async with client_as(world.db, outsider) as c:
        own = await c.get(f"/api/people/{outsider.id}")
        own_placements = await c.get(f"/api/people/{outsider.id}/organisaties")
        other = await c.get(f"/api/people/{world.person['viewer'].id}")
    assert own.status_code == 200, own.text
    assert own_placements.status_code == 200, own_placements.text
    assert other.status_code == 403
