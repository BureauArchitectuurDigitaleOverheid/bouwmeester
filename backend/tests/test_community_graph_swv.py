"""The community graph names samenwerkingsverbanden only to their readers.

``GET /samenwerkingsverbanden`` asks ``samenwerkingsverband:read``; the
graph asks the same before it adds their names.  ``platform_admin`` reads
people but not samenwerkingsverbanden.
"""

from datetime import date, timedelta

import pytest

from bouwmeester.models.lead import Lead
from bouwmeester.models.persoon_samenwerkingsverband import (
    PersoonSamenwerkingsverband,
)
from bouwmeester.models.resource_permission import ResourcePermission
from tests.factories import client_as


@pytest.fixture
async def graph_world(world):
    """The lead's assignee is in the world's samenwerkingsverband; the
    platform admin reads that lead through a role on it."""
    db = world.db
    lead = await db.get(Lead, world.res["lead"])
    lead.assignee_id = world.person["viewer"].id
    db.add_all(
        [
            PersoonSamenwerkingsverband(
                person_id=world.person["viewer"].id,
                samenwerkingsverband_id=world.res["samenwerkingsverband"],
                start_datum=date.today() - timedelta(days=1),
            ),
            ResourcePermission(
                person_id=world.person["platform_admin"].id,
                resource_type="lead",
                resource_id=lead.id,
                rol="opdrachtgever",
            ),
        ]
    )
    await db.flush()
    return world


async def _swv_nodes(world, who: str) -> list[dict]:
    async with client_as(world.db, world.person[who]) as c:
        resp = await c.get(
            "/api/graph/community",
            params={"initiatief_id": str(world.res["initiatief"])},
        )
    assert resp.status_code == 200, resp.text
    graph = resp.json()
    assert any(n["node_type"] == "lead" for n in graph["nodes"]), graph
    return [n for n in graph["nodes"] if n["node_type"] == "samenwerkingsverband"]


async def test_without_swv_read_no_names(graph_world):
    assert await _swv_nodes(graph_world, "platform_admin") == []


async def test_with_swv_read_names_shown(graph_world):
    [swv] = await _swv_nodes(graph_world, "afd_editor")
    assert swv["label"] == "Werkgroep"
