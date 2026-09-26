"""The remaining write domains on ``core/authz.py``.

Opdrachten, organisatie-eenheden (and their module toggles), tags,
samenwerkingsverbanden, stakeholder assessments, bijlagen and people.
Builds on the tree of ``test_authz`` (ministerie > DG > directie > afdeling
> team, plus a sibling directie "elders") and adds the resources of these
domains.  One table asks ``can()`` directly; a few route tests check that
the routes ask the same question.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can
from bouwmeester.models.bron import Bron
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.samenwerkingsverband import Samenwerkingsverband
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.models.tag import Tag
from tests.factories import client_as, grant_role, make_person, place
from tests.test_authz import World, _ctx, world  # noqa: F401  (fixture)


def _opdracht(titel: str, **kwargs) -> Opdracht:
    return Opdracht(type="opdracht", titel=titel, begrotingsjaar=2026, **kwargs)


@pytest.fixture
async def w(world: World) -> World:  # noqa: F811
    """The authz world plus opdrachten, tags, verbanden and assessments."""
    db: AsyncSession = world.db
    org = world.org

    org_admin = await make_person(db, "Directiebeheerder")
    await place(db, org_admin, org["directie"])
    await grant_role(db, org_admin, "ministry_admin", org["directie"])
    eenheid_eigenaar = await make_person(db, "Aanmaker stakeholder-eenheid")
    world.person.update(org_admin=org_admin, eenheid_eigenaar=eenheid_eigenaar)

    opdrachten = {
        "opdracht_afdeling": _opdracht("Afdeling", opdrachtgever_id=org["afdeling"].id),
        "opdracht_directie": _opdracht("Directie", opdrachtgever_id=org["directie"].id),
        # Client elsewhere, the team does the work: the team answers for it too.
        "opdracht_voor_team": _opdracht(
            "Voor team",
            opdrachtgever_id=org["elders"].id,
            opdrachtnemer_eenheid_id=org["team"].id,
        ),
        "opdracht_fcc": _opdracht("FCC-import", fcc_id=f"fcc-{uuid.uuid4().hex[:8]}"),
    }
    tag = Tag(name=f"authz-{uuid.uuid4().hex[:8]}")
    verband = Samenwerkingsverband(naam="Werkgroep", type="werkgroep")
    db.add_all([*opdrachten.values(), tag, verband])
    await db.flush()

    def assessment(scope_type: str, scope_id: uuid.UUID) -> StakeholderAssessment:
        return StakeholderAssessment(
            person_id=world.person["viewer"].id,
            scope_type=scope_type,
            scope_id=scope_id,
            belang=3,
        )

    assessments = {
        "sa_team": assessment("corpus_node", world.res["node_team"]),
        "sa_directie": assessment("corpus_node", world.res["node_directie"]),
        "sa_free": assessment("corpus_node", world.res["node_free"]),
        "sa_initiatief": assessment("initiatief", world.res["initiatief"]),
    }
    db.add_all(assessments.values())
    db.add_all(
        [
            ResourcePermission(
                person_id=world.person["role_only"].id,
                resource_type="opdracht",
                resource_id=opdrachten["opdracht_directie"].id,
                rol="eigenaar",
            ),
            ResourcePermission(
                person_id=eenheid_eigenaar.id,
                resource_type="organisatie_eenheid",
                resource_id=org["elders"].id,
                rol="eigenaar",
            ),
            Bron(id=world.res["node_team"]),
            Bron(id=world.res["node_directie"]),
        ]
    )
    await db.flush()

    world.res.update({k: v.id for k, v in opdrachten.items()})
    world.res.update({k: v.id for k, v in assessments.items()})
    world.res.update({f"eenheid_{k}": v.id for k, v in org.items()})
    world.res.update(tag=tag.id, verband=verband.id)
    return world


# (who, permission, resource type, resource key or None, eenheid key, expected)
CASES = [
    # Opdrachten: rights on the client or on the team doing the work.
    ("afd_editor", "opdracht:update", "opdracht", "opdracht_afdeling", None, True),
    ("afd_editor", "opdracht:update", "opdracht", "opdracht_directie", None, False),
    ("team_editor", "opdracht:update", "opdracht", "opdracht_voor_team", None, True),
    ("viewer", "opdracht:update", "opdracht", "opdracht_voor_team", None, False),
    ("manager", "opdracht:delete", "opdracht", "opdracht_afdeling", None, True),
    ("afd_editor", "opdracht:delete", "opdracht", "opdracht_afdeling", None, False),
    ("role_only", "opdracht:update", "opdracht", "opdracht_directie", None, True),
    ("role_only", "opdracht:delete", "opdracht", "opdracht_directie", None, True),
    ("role_only", "opdracht:update", "opdracht", "opdracht_afdeling", None, False),
    ("afd_editor", "opdracht:create", "opdracht", None, "team", True),
    ("afd_editor", "opdracht:create", "opdracht", None, "directie", False),
    ("platform_admin", "opdracht:update", "opdracht", "opdracht_afdeling", None, False),
    ("viewer", "opdracht:update", "opdracht", "opdracht_fcc", None, False),
    (
        "team_editor",
        "opdracht:update",
        "opdracht",
        "opdracht_fcc",
        None,
        True,
    ),
    (
        "team_editor",
        "opdracht:create",
        "opdracht",
        None,
        None,
        True,
    ),
    # Organisatie-eenheden: org:manage on the eenheid or above it.
    ("org_admin", "org:manage", "organisatie_eenheid", "eenheid_directie", None, True),
    ("org_admin", "org:manage", "organisatie_eenheid", "eenheid_team", None, True),
    ("org_admin", "org:manage", "organisatie_eenheid", "eenheid_dg", None, False),
    ("org_admin", "org:manage", "organisatie_eenheid", "eenheid_elders", None, False),
    ("team_editor", "org:manage", "organisatie_eenheid", "eenheid_team", None, False),
    ("manager", "org:manage", "organisatie_eenheid", "eenheid_directie", None, False),
    (
        "eenheid_eigenaar",
        "org:manage",
        "organisatie_eenheid",
        "eenheid_elders",
        None,
        True,
    ),
    (
        "eenheid_eigenaar",
        "org:manage",
        "organisatie_eenheid",
        "eenheid_dg",
        None,
        False,
    ),
    # Tags: one shared vocabulary, the permission through any role.
    ("team_editor", "tag:update", "tag", "tag", None, True),
    ("afd_editor", "tag:delete", "tag", "tag", None, False),
    ("manager", "tag:delete", "tag", "tag", None, True),
    ("viewer", "tag:update", "tag", "tag", None, False),
    ("role_only", "tag:create", "tag", None, None, False),
    # Samenwerkingsverbanden: tenant-wide, the permission through any role.
    (
        "team_editor",
        "samenwerkingsverband:update",
        "samenwerkingsverband",
        "verband",
        None,
        True,
    ),
    (
        "manager",
        "samenwerkingsverband:delete",
        "samenwerkingsverband",
        "verband",
        None,
        True,
    ),
    (
        "team_editor",
        "samenwerkingsverband:delete",
        "samenwerkingsverband",
        "verband",
        None,
        False,
    ),
    (
        "viewer",
        "samenwerkingsverband:update",
        "samenwerkingsverband",
        "verband",
        None,
        False,
    ),
    (
        "team_editor",
        "samenwerkingsverband:create",
        "samenwerkingsverband",
        None,
        None,
        True,
    ),
    (
        "role_only",
        "samenwerkingsverband:create",
        "samenwerkingsverband",
        None,
        None,
        False,
    ),
    # Stakeholder assessments: write access on their scope.
    (
        "team_editor",
        "stakeholder_assessment:update",
        "stakeholder_assessment",
        "sa_team",
        None,
        True,
    ),
    (
        "afd_editor",
        "stakeholder_assessment:delete",
        "stakeholder_assessment",
        "sa_team",
        None,
        True,
    ),
    (
        "team_editor",
        "stakeholder_assessment:update",
        "stakeholder_assessment",
        "sa_directie",
        None,
        False,
    ),
    (
        "viewer",
        "stakeholder_assessment:delete",
        "stakeholder_assessment",
        "sa_team",
        None,
        False,
    ),
    (
        "role_only",
        "stakeholder_assessment:update",
        "stakeholder_assessment",
        "sa_directie",
        None,
        True,
    ),
    (
        "role_only",
        "stakeholder_assessment:update",
        "stakeholder_assessment",
        "sa_initiatief",
        None,
        True,
    ),
    (
        "team_editor",
        "stakeholder_assessment:update",
        "stakeholder_assessment",
        "sa_initiatief",
        None,
        False,
    ),
    (
        "team_editor",
        "stakeholder_assessment:update",
        "stakeholder_assessment",
        "sa_free",
        None,
        True,
    ),
    (
        "afd_editor",
        "stakeholder_assessment:create",
        "initiatief",
        "initiatief",
        None,
        True,
    ),
    (
        "team_editor",
        "stakeholder_assessment:create",
        "initiatief",
        "initiatief",
        None,
        False,
    ),
    (
        "team_editor",
        "stakeholder_assessment:create",
        "corpus_node",
        "node_team",
        None,
        True,
    ),
    (
        "team_editor",
        "stakeholder_assessment:create",
        "corpus_node",
        "node_directie",
        None,
        False,
    ),
    # People: creating a contact is tenant-wide (placing it is guarded apart).
    (
        "team_editor",
        "people:create",
        "person",
        None,
        None,
        True,
    ),
    ("role_only", "people:create", "person", None, None, False),
]


def _case_id(case) -> str:
    return f"{case[0]}-{case[1]}-{case[3] or case[4] or 'new'}"


@pytest.mark.parametrize(
    ("who", "permission", "resource_type", "resource", "eenheid", "expected"),
    CASES,
    ids=[_case_id(c) for c in CASES],
)
async def test_can(w, who, permission, resource_type, resource, eenheid, expected):
    ctx = await _ctx(w, who)
    resource_id = w.res[resource] if resource else None
    eenheid_id = w.org[eenheid].id if eenheid else None
    got = await can(
        w.db, ctx, permission, resource_type, resource_id, eenheid_id=eenheid_id
    )
    assert got is expected


# ---------------------------------------------------------------------------
# Routes ask the same question
# ---------------------------------------------------------------------------


async def test_route_organisatie_edit_needs_rights_on_the_eenheid(w):
    async with client_as(w.db, w.person["org_admin"]) as c:
        below = await c.put(
            f"/api/organisatie/{w.org['afdeling'].id}", json={"naam": "Nieuw"}
        )
        above = await c.put(f"/api/organisatie/{w.org['dg'].id}", json={"naam": "Nee"})
    async with client_as(w.db, w.person["team_editor"]) as c:
        own_team = await c.put(
            f"/api/organisatie/{w.org['team'].id}", json={"naam": "Nee"}
        )
        delete_own_team = await c.delete(f"/api/organisatie/{w.org['team'].id}")
    async with client_as(w.db, w.person["eenheid_eigenaar"]) as c:
        owned = await c.put(
            f"/api/organisatie/{w.org['elders'].id}", json={"naam": "Eigen"}
        )
    assert below.status_code == 200, below.text
    assert above.status_code == 403
    assert own_team.status_code == 403
    assert delete_own_team.status_code == 403
    assert owned.status_code == 200, owned.text


async def test_route_eenheid_modules_need_org_manage_on_the_eenheid(w):
    body = {"module": "leads", "enabled": False}
    async with client_as(w.db, w.person["org_admin"]) as c:
        below = await c.put(f"/api/eenheid-modules/{w.org['team'].id}", json=body)
        sibling = await c.put(f"/api/eenheid-modules/{w.org['elders'].id}", json=body)
    async with client_as(w.db, w.person["manager"]) as c:
        manager = await c.put(f"/api/eenheid-modules/{w.org['team'].id}", json=body)
    assert below.status_code == 200, below.text
    assert sibling.status_code == 403
    assert manager.status_code == 403


async def test_route_opdracht_create_and_move_check_the_place(w):
    new = {
        "type": "opdracht",
        "titel": "Nieuw",
        "begrotingsjaar": 2026,
        "instrument_id": str(w.res["node_team"]),
    }
    async with client_as(w.db, w.person["afd_editor"]) as c:
        in_team = await c.post(
            "/api/opdrachten", json={**new, "opdrachtgever_id": str(w.org["team"].id)}
        )
        in_directie = await c.post(
            "/api/opdrachten",
            json={**new, "opdrachtgever_id": str(w.org["directie"].id)},
        )
        moved_up = await c.put(
            f"/api/opdrachten/{w.res['opdracht_afdeling']}",
            json={"opdrachtgever_id": str(w.org["directie"].id)},
        )
        visible_only = await c.put(
            f"/api/opdrachten/{w.res['opdracht_directie']}", json={"titel": "Nee"}
        )
        bulk = await c.post("/api/opdrachten/match-contacts-bulk")
    assert in_team.status_code == 201, in_team.text
    assert in_directie.status_code == 403
    assert moved_up.status_code == 403
    assert visible_only.status_code == 403
    assert bulk.status_code == 403


async def test_route_tags_are_tenant_wide(w):
    async with client_as(w.db, w.person["team_editor"]) as c:
        editor = await c.put(f"/api/tags/{w.res['tag']}", json={"name": "hernoemd"})
    async with client_as(w.db, w.person["viewer"]) as c:
        viewer = await c.put(f"/api/tags/{w.res['tag']}", json={"name": "nee"})
        created = await c.post("/api/tags", json={"name": "nee"})
    assert editor.status_code == 200, editor.text
    assert viewer.status_code == 403
    assert created.status_code == 403


async def test_route_stakeholder_assessment_follows_its_scope(w):
    async with client_as(w.db, w.person["team_editor"]) as c:
        on_team = await c.post(
            "/api/stakeholder-assessments",
            json={
                "person_id": str(w.person["manager"].id),
                "scope_type": "corpus_node",
                "scope_id": str(w.res["node_team"]),
                "belang": 4,
            },
        )
        on_directie = await c.post(
            "/api/stakeholder-assessments",
            json={
                "person_id": str(w.person["manager"].id),
                "scope_type": "corpus_node",
                "scope_id": str(w.res["node_directie"]),
                "belang": 4,
            },
        )
        edit_directie = await c.put(
            f"/api/stakeholder-assessments/{w.res['sa_directie']}", json={"belang": 1}
        )
        delete_team = await c.delete(f"/api/stakeholder-assessments/{w.res['sa_team']}")
    assert on_team.status_code == 201, on_team.text
    assert on_directie.status_code == 403
    assert edit_directie.status_code == 403
    assert delete_team.status_code == 204


async def test_route_bijlage_needs_node_update_on_the_node(w):
    pdf = ("bijlage.pdf", b"%PDF-1.4\n%test\n", "application/pdf")
    async with client_as(w.db, w.person["team_editor"]) as c:
        on_team = await c.post(
            f"/api/nodes/{w.res['node_team']}/bijlage", files={"file": pdf}
        )
        on_directie = await c.post(
            f"/api/nodes/{w.res['node_directie']}/bijlage", files={"file": pdf}
        )
        delete_directie = await c.delete(f"/api/nodes/{w.res['node_directie']}/bijlage")
    assert on_team.status_code == 201, on_team.text
    assert on_directie.status_code == 403
    assert delete_directie.status_code == 403


async def test_route_samenwerkingsverband_is_tenant_wide(w):
    async with client_as(w.db, w.person["team_editor"]) as c:
        editor = await c.put(
            f"/api/samenwerkingsverbanden/{w.res['verband']}", json={"naam": "Ja"}
        )
        editor_delete = await c.delete(
            f"/api/samenwerkingsverbanden/{w.res['verband']}"
        )
    async with client_as(w.db, w.person["viewer"]) as c:
        viewer = await c.post(
            f"/api/samenwerkingsverbanden/{w.res['verband']}/leden",
            json={"person_id": str(w.person["viewer"].id)},
        )
    assert editor.status_code == 200, editor.text
    assert editor_delete.status_code == 403
    assert viewer.status_code == 403


async def test_route_create_person_needs_people_create(w):
    async with client_as(w.db, w.person["role_only"]) as c:
        resp = await c.post("/api/people", json={"naam": "Geen rol"})
    assert resp.status_code == 403
