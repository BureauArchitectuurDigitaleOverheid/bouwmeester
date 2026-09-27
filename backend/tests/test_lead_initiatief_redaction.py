"""A lead read through a role on the lead names no initiatief it cannot read.

An ``opdrachtgever`` of one lead reads that lead, not its initiatief.  The
embedded initiatief summary (name, colour) is part of the initiatief, so it
is left out; ``initiatief_id`` stays, it is part of the lead.
"""

import pytest

from bouwmeester.models.resource_permission import ResourcePermission
from tests.factories import client_as, make_org, make_person, place


@pytest.fixture
async def opdrachtgever(world):
    far = await make_org(world.db, "Ver weg", "ministerie")
    person = await make_person(world.db, "Opdrachtgever")
    await place(world.db, person, far)
    world.db.add(
        ResourcePermission(
            person_id=person.id,
            resource_type="lead",
            resource_id=world.res["lead"],
            rol="opdrachtgever",
        )
    )
    await world.db.flush()
    return person


def _only(leads, lead_id):
    return next(item for item in leads if item["id"] == str(lead_id))


async def test_list_redacts_unreadable_initiatief(world, opdrachtgever):
    async with client_as(world.db, opdrachtgever) as c:
        resp = await c.get("/api/leads")
    assert resp.status_code == 200, resp.text
    lead = _only(resp.json(), world.res["lead"])
    assert lead["initiatief_id"] == str(world.res["initiatief"])
    assert lead["initiatief"] is None


async def test_detail_redacts_unreadable_initiatief(world, opdrachtgever):
    async with client_as(world.db, opdrachtgever) as c:
        resp = await c.get(f"/api/leads/{world.res['lead']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["initiatief"] is None


async def test_reader_of_the_initiatief_keeps_the_summary(world):
    async with client_as(world.db, world.person["afd_editor"]) as c:
        resp = await c.get("/api/leads")
    lead = _only(resp.json(), world.res["lead"])
    assert lead["initiatief"]["id"] == str(world.res["initiatief"])
