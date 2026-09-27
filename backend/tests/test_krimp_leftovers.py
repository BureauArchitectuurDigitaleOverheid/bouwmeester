"""Ending a placement asked by its id, and grants held at an unproven first login."""

import uuid

from sqlalchemy import select

from bouwmeester.core.auth import get_or_create_person
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PLACEMENT_BRON_HANDMATIG
from bouwmeester.models.resource_permission import ResourcePermission
from tests.authz_world import World
from tests.factories import client_as, make_person, place


async def _may_end(w: World, who: str, person_id, placement_id) -> bool:
    body = {
        "evaluations": [
            {
                "action": "person:place",
                "resource": {
                    "type": "person",
                    "id": str(person_id),
                    "properties": {"ending": True, "placement_id": str(placement_id)},
                },
            }
        ]
    }
    async with client_as(w.db, w.person[who]) as c:
        resp = await c.post("/api/authz/evaluations", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["evaluations"][0]["decision"]


async def test_evaluation_ends_a_placement_on_its_bron(world: World):
    contact = await make_person(world.db, "Contact", account=False)
    trusted = await place(world.db, contact, world.org["team"])
    informational = await place(
        world.db, contact, world.org["sibling_team"], bron=PLACEMENT_BRON_HANDMATIG
    )
    assert not await _may_end(world, "team_editor", contact.id, trusted.id)
    assert await _may_end(world, "team_editor", contact.id, informational.id)
    assert await _may_end(world, "manager", contact.id, trusted.id)
    # A placement of someone else than the person asked about: no.
    assert not await _may_end(world, "manager", world.person["viewer"].id, trusted.id)


async def _contact_with_grant(w: World, added_by: Person) -> tuple[Person, str]:
    contact = await make_person(w.db, "Nieuwe collega", account=False)
    alt = f"alt-{uuid.uuid4().hex[:8]}@example.com"
    w.db.add(PersonEmail(person_id=contact.id, email=alt, added_by_id=added_by.id))
    w.db.add(
        ResourcePermission(
            person_id=contact.id,
            resource_type="corpus_node",
            resource_id=w.res["node_team"],
            rol="betrokken",
        )
    )
    await w.db.flush()
    return contact, alt


async def _grants(w: World, person: Person) -> list[ResourcePermission]:
    return list(
        (
            await w.db.scalars(
                select(ResourcePermission).where(
                    ResourcePermission.person_id == person.id
                )
            )
        ).all()
    )


async def test_unproven_login_holds_resource_grants(world: World):
    contact, alt = await _contact_with_grant(world, world.person["viewer"])
    person = await get_or_create_person(
        world.db, "sub-grant", alt, "Nieuwe collega", email_verified=True
    )
    assert person.id == contact.id
    assert await _grants(world, contact) == []


async def test_login_keeps_grants_the_adder_could_hand_out(world: World):
    contact, alt = await _contact_with_grant(world, world.person["team_editor"])
    await get_or_create_person(
        world.db, "sub-grant-ok", alt, "Nieuwe collega", email_verified=True
    )
    assert len(await _grants(world, contact)) == 1
