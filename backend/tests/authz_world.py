"""The shared authorization test world and helpers for its tables.

A realistic tree (ministerie > DG > directie > afdeling > team, plus a
sibling directie ``elders`` and a sibling team) with mixed roles and real
permission resolution.  ``world`` is the tree; ``iw`` adds the roles only
initiatieven care about.  The fixtures are registered in ``conftest.py``;
test modules import the helpers from here, never from each other.

Table helpers:

- ``assert_can_case(world, case)`` decides one ``can()`` case,
  ``(who, permission, resource type, resource key, eenheid key, expected)``;
- ``assert_route_case(world, who, method, path, body, expected)`` sends one
  request, with ``{key}`` in the path filled from ``world.res`` and a body
  that may be a builder taking the world.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can
from bouwmeester.core.permissions import PermissionContext, build_permission_context
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
from bouwmeester.models.task import Task
from bouwmeester.repositories.lead_column import LeadColumnRepository
from tests.factories import client_as, grant_role, make_org, make_person, place


@dataclass
class World:
    db: AsyncSession
    org: dict[str, OrganisatieEenheid]
    person: dict[str, Person]
    # Resource ids by key; ``edge_type`` is the (string) id of the edge type
    # the world's edges use.
    res: dict[str, Any]

    def id(self, key: str) -> uuid.UUID:
        """The id of a resource, or of an eenheid when no resource has *key*."""
        return self.res[key] if key in self.res else self.org[key].id


async def make_node(db: AsyncSession, title: str, eenheid=None) -> CorpusNode:
    node = CorpusNode(
        id=uuid.uuid4(),
        title=title,
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=eenheid.id if eenheid else None,
    )
    db.add(node)
    await db.flush()
    return node


async def make_item(
    w: World, node_key: str | None = None, status: str = "imported"
) -> ParlementairItem:
    """A parliamentary item on one of the world's nodes (or on none yet)."""
    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-1",
        titel="Motie",
        onderwerp="Authz",
        bron="tweede_kamer",
        datum=date(2026, 1, 1),
        status=status,
        corpus_node_id=w.res[node_key] if node_key else None,
    )
    w.db.add(item)
    await w.db.flush()
    return item


async def add_directie_admin(w: World, key: str, naam: str) -> Person:
    """A ministry_admin placed in and scoped to the directie."""
    admin = await make_person(w.db, naam)
    await place(w.db, admin, w.org["directie"])
    await grant_role(w.db, admin, "ministry_admin", w.org["directie"])
    w.person[key] = admin
    return admin


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    db = db_session
    ministerie = await make_org(db, "Ministerie", "ministerie")
    dg = await make_org(db, "DG", "directoraat_generaal", ministerie)
    directie = await make_org(db, "Directie", "directie", dg)
    afdeling = await make_org(db, "Afdeling", "afdeling", directie)
    team = await make_org(db, "Team", "team", afdeling)
    elders = await make_org(db, "Elders", "directie", dg)
    sibling_team = await make_org(db, "Ander team", "team", afdeling)

    # Only super_admin and platform_admin exist as system roles.
    platform_admin = await make_person(db, "Platformbeheerder")
    await grant_role(db, platform_admin, "platform_admin")

    afd_editor = await make_person(db, "Afdelingsredacteur")
    await place(db, afd_editor, afdeling)
    await grant_role(db, afd_editor, "editor", afdeling)

    team_editor = await make_person(db, "Teamredacteur")
    await place(db, team_editor, team)
    await grant_role(db, team_editor, "editor", team)

    viewer = await make_person(db, "Teamlid")  # implicit viewer
    await place(db, viewer, team)

    role_only = await make_person(db, "Alleen resource-rol")
    manager = await make_person(db, "Directeur")
    await place(db, manager, directie)
    await grant_role(db, manager, "unit_manager", directie)

    super_admin = await make_person(db, "Systeembeheerder")
    await grant_role(db, super_admin, "super_admin")

    node_directie = await make_node(db, "Directiedossier", directie)
    node_afdeling = await make_node(db, "Afdelingsdossier", afdeling)
    node_team = await make_node(db, "Teamdossier", team)
    node_elders = await make_node(db, "Dossier elders", elders)
    node_free = await make_node(db, "Dossier zonder eenheid")
    node_sibling = await make_node(db, "Dossier ander team", sibling_team)
    opdracht_free = Opdracht(type="opdracht", titel="FCC-import", begrotingsjaar=2026)
    opdracht_directie = Opdracht(
        type="opdracht",
        titel="Directie-opdracht",
        begrotingsjaar=2026,
        opdrachtgever_id=directie.id,
    )
    samenwerkingsverband = Samenwerkingsverband(naam="Werkgroep", type="werkgroep")
    db.add_all([opdracht_free, opdracht_directie, samenwerkingsverband])
    db.add(
        ResourcePermission(
            person_id=role_only.id,
            resource_type="corpus_node",
            resource_id=node_directie.id,
            rol="betrokken",
        )
    )

    et = EdgeType(id=f"authz_{uuid.uuid4().hex[:8]}", label_nl="T", label_en="T")
    db.add(et)
    await db.flush()
    edge_team_directie = Edge(
        from_node_id=node_team.id, to_node_id=node_directie.id, edge_type_id=et.id
    )
    edge_directie_elders = Edge(
        from_node_id=node_directie.id, to_node_id=node_elders.id, edge_type_id=et.id
    )
    db.add_all([edge_team_directie, edge_directie_elders])

    task_team = Task(
        title="Teamtaak",
        node_id=node_directie.id,
        organisatie_eenheid_id=team.id,
        status="open",
    )
    task_on_team_node = Task(
        title="Taak zonder eenheid", node_id=node_team.id, status="open"
    )
    task_elders = Task(
        title="Taak elders",
        node_id=node_elders.id,
        organisatie_eenheid_id=elders.id,
        status="open",
    )
    db.add_all([task_team, task_on_team_node, task_elders])

    initiatief = Initiatief(id=uuid.uuid4(), naam=f"Init {uuid.uuid4().hex[:6]}")
    db.add(initiatief)
    await db.flush()
    db.add_all(
        [
            ResourcePermission(
                organisatie_eenheid_id=afdeling.id,
                resource_type="initiatief",
                resource_id=initiatief.id,
                rol="eigenaar",
            ),
            ResourcePermission(
                person_id=role_only.id,
                resource_type="initiatief",
                resource_id=initiatief.id,
                rol="contributor",
            ),
        ]
    )
    lead = Lead(title="Lead", stage="verkennen", initiatief_id=initiatief.id)
    lead_free = Lead(title="Losse lead", stage="verkennen")
    db.add_all([lead, lead_free])
    await db.flush()
    await LeadColumnRepository(db).seed_defaults(initiatief.id)
    column = await db.scalar(
        select(LeadColumn.id).where(LeadColumn.initiatief_id == initiatief.id).limit(1)
    )

    return World(
        db=db,
        org={
            "ministerie": ministerie,
            "dg": dg,
            "directie": directie,
            "afdeling": afdeling,
            "team": team,
            "elders": elders,
            "sibling_team": sibling_team,
        },
        person={
            "platform_admin": platform_admin,
            "afd_editor": afd_editor,
            "team_editor": team_editor,
            "viewer": viewer,
            "role_only": role_only,
            "manager": manager,
            "super_admin": super_admin,
        },
        res={
            "eenheid_elders": elders.id,
            "eenheid_team": team.id,
            "node_directie": node_directie.id,
            "node_afdeling": node_afdeling.id,
            "node_team": node_team.id,
            "node_elders": node_elders.id,
            "node_free": node_free.id,
            "node_sibling": node_sibling.id,
            "opdracht_free": opdracht_free.id,
            "samenwerkingsverband": samenwerkingsverband.id,
            "opdracht_directie": opdracht_directie.id,
            "edge_team_directie": edge_team_directie.id,
            "edge_directie_elders": edge_directie_elders.id,
            "task_team": task_team.id,
            "task_on_team_node": task_on_team_node.id,
            "task_elders": task_elders.id,
            "initiatief": initiatief.id,
            "lead": lead.id,
            "lead_free": lead_free.id,
            "lead_column": column,
            "edge_type": et.id,
        },
    )


@pytest.fixture
async def iw(world: World) -> World:
    """The world plus the roles only initiatieven care about.

    The initiatief is owned by the afdeling (eenheid-level eigenaar) and
    ``role_only`` is a direct contributor.  Added: a viewer through a
    resource role, a partner eenheid as contributor, a directie admin who may
    share, and a Mattermost channel linked to the initiatief.
    """
    db = world.db
    initiatief_id = world.res["initiatief"]

    rp_viewer = await make_person(db, "Kijker")
    partner = await make_org(db, "Partnerteam", "team", world.org["elders"])
    partner_member = await make_person(db, "Partnerlid")
    await place(db, partner_member, partner)
    db.add_all(
        [
            ResourcePermission(
                person_id=rp_viewer.id,
                resource_type="initiatief",
                resource_id=initiatief_id,
                rol="viewer",
            ),
            ResourcePermission(
                organisatie_eenheid_id=partner.id,
                resource_type="initiatief",
                resource_id=initiatief_id,
                rol="contributor",
            ),
        ]
    )
    # Shares need org:manage; ministry_admin carries it, scoped to the directie.
    await add_directie_admin(world, "org_admin", "Directiebeheerder")

    link = MattermostChannelLink(
        channel_id="a" * 26,
        channel_name="init-kanaal",
        channel_display_name="Init kanaal",
        scope_type="initiatief",
        scope_id=initiatief_id,
    )
    db.add(link)
    await db.flush()

    world.person.update(rp_viewer=rp_viewer, partner_member=partner_member)
    world.org["partner"] = partner
    world.res["channel_link"] = link.id
    return world


async def perm_ctx(w: World, who: str) -> PermissionContext:
    """The real permission context of one of the world's people."""
    return await build_permission_context(w.db, w.person[who])


async def rights_level(db, ctx, initiatief_id) -> str | None:
    """The strongest of delete/update/read held on an initiatief, as a rol name."""
    for level, permission in (
        ("eigenaar", "initiatief:delete"),
        ("contributor", "initiatief:update"),
        ("viewer", "initiatief:read"),
    ):
        if await can(db, ctx, permission, "initiatief", initiatief_id):
            return level
    return None


def ask(action: str, resource_type: str, resource_id=None, **properties) -> dict:
    """One AuthZEN evaluation for ``POST /api/authz/evaluations``."""
    resource: dict = {"type": resource_type}
    if resource_id is not None:
        resource["id"] = str(resource_id)
    if properties:
        resource["properties"] = {
            k: v if isinstance(v, bool) else str(v) for k, v in properties.items()
        }
    return {"action": action, "resource": resource}


# A can() case: (who, permission, resource type, resource key or None,
# eenheid key or None, expected).
CanCase = tuple[str, str, str, str | None, str | None, bool]


def can_case_id(case: CanCase) -> str:
    return f"{case[0]}-{case[1]}-{case[3] or case[4] or 'new'}"


async def assert_can_case(w: World, case: CanCase) -> None:
    who, permission, resource_type, resource, eenheid, expected = case
    got = await can(
        w.db,
        await perm_ctx(w, who),
        permission,
        resource_type,
        w.id(resource) if resource else None,
        eenheid_id=w.id(eenheid) if eenheid else None,
    )
    assert got is expected, case


# A route case: (who, method, path template, body or body builder, status).
RouteCase = tuple[str, str, str, Any, int]


def route_case_id(case: RouteCase) -> str:
    return f"{case[0]}-{case[1]}-{case[2]}"


async def assert_route_case(
    w: World,
    who: str,
    method: str,
    path: str,
    body: dict | Callable[[World], dict] | None,
    expected: int,
) -> None:
    url = path.format(**w.res)
    kwargs = {}
    if body is not None:
        kwargs["json"] = body(w) if callable(body) else body
    async with client_as(w.db, w.person[who]) as c:
        resp = await c.request(method, url, **kwargs)
    assert resp.status_code == expected, (who, method, url, resp.text)
