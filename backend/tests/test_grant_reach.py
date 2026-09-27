"""Grants that must not reach further than the grantor's own authority.

Round-2 review findings on ``core/authority.py``, on the shared ``world``
(tests/authz_world.py): taking over a pre-account through its emails,
sharing an eenheid with yourself, role routes that asked more than the
guard, and eenheid grants that reach the grantor later.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from bouwmeester.core.authority import require_can_grant_resource_role
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.role import PersonRole
from tests.authz_world import World, add_directie_admin, perm_ctx
from tests.factories import YESTERDAY, client_as, make_org, make_person

# ---------------------------------------------------------------------------
# Identity of a person who already holds access (B3)
# ---------------------------------------------------------------------------


async def _contact_in(w: World, eenheid_key: str, bron: str):
    """A person without login, placed in one of the world's eenheden."""
    contact = await make_person(w.db, "Nieuwe collega", account=False)
    w.db.add(
        PersonOrganisatieEenheid(
            person_id=contact.id,
            organisatie_eenheid_id=w.org[eenheid_key].id,
            start_datum=YESTERDAY,
            bron=bron,
        )
    )
    await w.db.flush()
    return contact


async def _add_email(w: World, who: str, person) -> int:
    async with client_as(w.db, w.person[who]) as c:
        resp = await c.post(
            f"/api/people/{person.id}/emails",
            json={"email": f"overname-{uuid.uuid4().hex[:8]}@example.com"},
        )
    return resp.status_code


async def test_viewer_cannot_add_email_to_placed_new_hire(world: World):
    """A confirmed placement goes with the record at first login."""
    new_hire = await _contact_in(world, "team", "leidinggevende")
    assert await _add_email(world, "viewer", new_hire) == 403


async def test_manager_adds_email_to_own_new_hire(world: World):
    new_hire = await _contact_in(world, "team", "leidinggevende")
    assert await _add_email(world, "manager", new_hire) == 201


async def test_imported_internal_placement_counts_as_confirmed(world: World):
    kept_at_login = await _contact_in(world, "team", "roo_leidinggevende")
    assert await _add_email(world, "viewer", kept_at_login) == 403


async def test_unconfirmed_placement_leaves_contact_editable(world: World):
    """A manual placement becomes a request at first login: nothing to take."""
    contact = await _contact_in(world, "team", "handmatig")
    assert await _add_email(world, "viewer", contact) == 201


async def test_assigned_task_needs_task_authority_for_email(world: World):
    """The assignee reads the task: that goes with the record at first login."""
    from bouwmeester.models.task import Task

    contact = await make_person(world.db, "Opdrachtnemer", account=False)
    task = await world.db.get(Task, world.res["task_elders"])
    task.assignee_id = contact.id
    await world.db.flush()

    assert await _add_email(world, "viewer", contact) == 403
    assert await _add_email(world, "super_admin", contact) == 201


async def test_trusted_external_placement_counts_once_it_reaches_something(
    world: World,
):
    gemeente = await make_org(world.db, "Gemeente", "gemeente")
    world.org["gemeente"] = gemeente
    contact = await _contact_in(world, "gemeente", "tk_odata")
    world.db.add(
        ResourcePermission(
            organisatie_eenheid_id=gemeente.id,
            resource_type="initiatief",
            resource_id=world.res["initiatief"],
            rol="contributor",
        )
    )
    await world.db.flush()
    assert await _add_email(world, "viewer", contact) == 403


async def test_external_contact_stays_editable(world: World):
    gemeente = await make_org(world.db, "Gemeente", "gemeente")
    world.org["gemeente"] = gemeente
    contact = await _contact_in(world, "gemeente", "tk_odata")
    assert await _add_email(world, "viewer", contact) == 201


async def test_resource_grant_needs_grant_authority_for_email(world: World):
    stakeholder = await make_person(world.db, "Betrokkene", account=False)
    world.db.add(
        ResourcePermission(
            person_id=stakeholder.id,
            resource_type="corpus_node",
            resource_id=world.res["node_directie"],
            rol="betrokken",
        )
    )
    await world.db.flush()
    assert await _add_email(world, "viewer", stakeholder) == 403
    assert await _add_email(world, "manager", stakeholder) == 201


async def test_profile_of_placed_new_hire_stays_editable(world: World):
    """Only emails decide identity; the naam and functie do not."""
    new_hire = await _contact_in(world, "team", "leidinggevende")
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.put(f"/api/people/{new_hire.id}", json={"functie": "Nieuw"})
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Sharing is a grant (B10)
# ---------------------------------------------------------------------------


def _share(w: World, target: str) -> dict:
    return {
        "source_eenheid_id": str(w.org["afdeling"].id),
        "target_eenheid_id": str(w.org[target].id),
        "access_level": "edit",
    }


@pytest.mark.parametrize(
    ("target", "expected"),
    [("directie", 403), ("elders", 200)],
    ids=["own-eenheid", "other-eenheid"],
)
async def test_nobody_shares_with_their_own_eenheid(world: World, target, expected):
    await add_directie_admin(world, "org_admin", "Directiebeheerder")
    async with client_as(world.db, world.person["org_admin"]) as c:
        resp = await c.post("/api/sharing", json=_share(world, target))
    assert resp.status_code == expected, resp.text


async def test_nobody_shares_with_an_eenheid_they_asked_to_join(world: World):
    admin = await add_directie_admin(world, "org_admin", "Directiebeheerder")
    world.db.add(
        OrgPlacementRequest(
            person_id=admin.id,
            organisatie_eenheid_id=world.org["elders"].id,
            dienstverband="in_dienst",
        )
    )
    await world.db.flush()
    async with client_as(world.db, admin) as c:
        resp = await c.post("/api/sharing", json=_share(world, "elders"))
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Role routes: the guard decides, not a permission in front of it
# ---------------------------------------------------------------------------


async def test_editor_gives_up_own_role(world: World):
    """No ``people:assign_role`` needed to give up your own role."""
    editor = world.person["team_editor"]
    assignment = await world.db.scalar(
        select(PersonRole.id).where(PersonRole.person_id == editor.id)
    )
    async with client_as(world.db, editor) as c:
        resp = await c.delete(f"/api/roles/assignments/{assignment}")
    assert resp.status_code == 200, resp.text


async def test_editor_still_cannot_assign_roles(world: World):
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            "/api/roles/assign",
            json={
                "person_id": str(world.person["viewer"].id),
                "role_id": "editor",
                "organisatie_eenheid_id": str(world.org["team"].id),
            },
        )
    assert resp.status_code == 403, resp.text


async def test_person_without_placement_edits_own_email(world: World):
    """Your own record needs no ``people:update`` (role_only has no placement)."""
    assert await _add_email(world, "role_only", world.person["role_only"]) == 201


# ---------------------------------------------------------------------------
# Eenheid grants never reach the grantor, not even later
# ---------------------------------------------------------------------------


async def _grant_to_eenheid(w: World, who: str, eenheid) -> None:
    """afdeling is eigenaar of the initiatief, so its editor hands out roles."""
    await require_can_grant_resource_role(
        w.db,
        await perm_ctx(w, who),
        resource_type="initiatief",
        resource_id=w.res["initiatief"],
        rol="contributor",
        target_eenheid_id=eenheid.id,
    )


async def test_grant_to_new_sub_eenheid_cannot_be_joined_by_the_grantor(
    world: World,
):
    """A fresh sub-eenheid has no members; the grantor cannot become one."""
    sub = await make_org(world.db, "Nieuw team", "team", world.org["afdeling"])
    await _grant_to_eenheid(world, "afd_editor", sub)
    editor = world.person["afd_editor"]
    async with client_as(world.db, editor) as c:
        resp = await c.post(
            f"/api/people/{editor.id}/organisaties",
            json={
                "organisatie_eenheid_id": str(sub.id),
                "start_datum": date.today().isoformat(),
            },
        )
    assert resp.status_code == 403, resp.text


async def test_grant_to_eenheid_the_grantor_asked_to_join(world: World):
    sub = await make_org(world.db, "Nieuw team", "team", world.org["afdeling"])
    world.db.add(
        OrgPlacementRequest(
            person_id=world.person["afd_editor"].id,
            organisatie_eenheid_id=sub.id,
            dienstverband="in_dienst",
        )
    )
    await world.db.flush()
    with pytest.raises(HTTPException) as exc:
        await _grant_to_eenheid(world, "afd_editor", sub)
    assert exc.value.status_code == 403


async def test_grant_to_eenheid_the_grantor_joins_later(world: World):
    sub = await make_org(world.db, "Nieuw team", "team", world.org["afdeling"])
    world.db.add(
        PersonOrganisatieEenheid(
            person_id=world.person["afd_editor"].id,
            organisatie_eenheid_id=sub.id,
            start_datum=date.today() + timedelta(days=7),
            bron="leidinggevende",
        )
    )
    await world.db.flush()
    with pytest.raises(HTTPException) as exc:
        await _grant_to_eenheid(world, "afd_editor", sub)
    assert exc.value.status_code == 403
