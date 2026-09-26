"""Reads: one visibility rule per resource type, the same for lists and details.

Builds on the tree of ``test_authz.world`` (plus the extra roles of
``test_authz_initiatief.iw``) and adds initiatieven owned higher and
elsewhere in the tree, a personal initiatief, and leads whose only link to
a reader is a lead role.  For every person the list and the detail must
agree, and whoever may write something must also see it.
"""

import uuid
from unittest.mock import patch

import pytest

from bouwmeester.core.authz import can
from bouwmeester.core.permissions import build_permission_context
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.services.llm.base import EdgeRelevanceResult
from tests.factories import client_as, make_person, place
from tests.test_authz import World, world  # noqa: F401  (shared fixture)
from tests.test_authz_initiatief import iw  # noqa: F401  (shared fixture)


async def _initiatief(db, naam: str, **owner) -> uuid.UUID:
    init = Initiatief(id=uuid.uuid4(), naam=f"{naam} {uuid.uuid4().hex[:6]}")
    db.add(init)
    await db.flush()
    db.add(
        ResourcePermission(
            resource_type="initiatief", resource_id=init.id, rol="eigenaar", **owner
        )
    )
    await db.flush()
    return init.id


@pytest.fixture
async def rw(iw: World) -> World:  # noqa: F811
    db = iw.db
    org = iw.org

    # A plain member high in the tree: reads up, not down.
    dg_member = await make_person(db, "DG-lid")
    await place(db, dg_member, org["dg"])
    # Someone elsewhere with a role on one lead only.
    outsider = await make_person(db, "Buitenstaander")
    await place(db, outsider, org["elders"])
    lead_contact = await make_person(db, "Leadcontact")
    lead_owner = await make_person(db, "Opdrachtgever")

    init_dg = await _initiatief(
        db, "DG-initiatief", organisatie_eenheid_id=org["dg"].id
    )
    init_elders = await _initiatief(
        db, "Elders-initiatief", organisatie_eenheid_id=org["elders"].id
    )
    init_personal = await _initiatief(
        db, "Eigen initiatief", person_id=iw.person["role_only"].id
    )

    lead_elders = Lead(
        title="Lead elders", stage="verkennen", initiatief_id=init_elders
    )
    lead_dg = Lead(title="Lead DG", stage="verkennen", initiatief_id=init_dg)
    lead_personal = Lead(
        title="Eigen lead", stage="verkennen", initiatief_id=init_personal
    )
    db.add_all([lead_elders, lead_dg, lead_personal])
    await db.flush()
    db.add_all(
        [
            # an opdrachtgever outside the initiatief can write the lead
            ResourcePermission(
                person_id=outsider.id,
                resource_type="lead",
                resource_id=lead_dg.id,
                rol="opdrachtgever",
            ),
            ResourcePermission(
                person_id=lead_owner.id,
                resource_type="lead",
                resource_id=iw.res["lead"],
                rol="opdrachtgever",
            ),
            # a contact without any other link
            ResourcePermission(
                person_id=lead_contact.id,
                resource_type="lead",
                resource_id=lead_elders.id,
                rol="contactpersoon",
            ),
            # a lead role held by a whole eenheid
            ResourcePermission(
                organisatie_eenheid_id=org["team"].id,
                resource_type="lead",
                resource_id=lead_personal.id,
                rol="betrokken",
            ),
        ]
    )
    await db.flush()

    iw.person.update(
        dg_member=dg_member,
        outsider=outsider,
        lead_contact=lead_contact,
        lead_owner=lead_owner,
    )
    iw.res.update(
        init_dg=init_dg,
        init_elders=init_elders,
        init_personal=init_personal,
        lead_elders=lead_elders.id,
        lead_dg=lead_dg.id,
        lead_personal=lead_personal.id,
    )
    return iw


def _ids(w: World, *keys: str) -> set[uuid.UUID]:
    return {w.res[k] for k in keys}


INITIATIEVEN = ("initiatief", "init_dg", "init_elders", "init_personal")
LEADS = ("lead", "lead_free", "lead_elders", "lead_dg", "lead_personal")


async def _listed(c, path: str, universe: set[uuid.UUID], key="id") -> set:
    resp = await c.get(path, params={"limit": 500})
    assert resp.status_code == 200, resp.text
    return {uuid.UUID(item[key]) for item in resp.json()} & universe


async def _readable(c, template: str, ids: set[uuid.UUID]) -> set:
    found = set()
    for rid in ids:
        resp = await c.get(template.format(rid))
        assert resp.status_code in (200, 404), resp.text
        if resp.status_code == 200:
            found.add(rid)
    return found


# ---------------------------------------------------------------------------
# Initiatieven
# ---------------------------------------------------------------------------


async def test_initiatief_list_equals_detail_for_everyone(rw):
    universe = _ids(rw, *INITIATIEVEN)
    for who, person in rw.person.items():
        async with client_as(rw.db, person) as c:
            listed = await _listed(c, "/api/initiatieven", universe)
            readable = await _readable(c, "/api/initiatieven/{}", universe)
        assert listed == readable, who


# Who sees which initiatief (owners: afdeling, DG, elders, role_only personally).
SEES_INITIATIEVEN = {
    "super_admin": INITIATIEVEN,
    "manager": ("initiatief", "init_dg"),  # manages the directie below the DG
    "afd_editor": ("initiatief", "init_dg"),  # own afdeling, and up the line
    "viewer": ("initiatief", "init_dg"),  # a team member reads up the line
    "team_editor": ("initiatief", "init_dg"),
    "role_only": ("initiatief", "init_personal"),  # resource roles only
    "dg_member": ("init_dg",),  # does not read down into the afdeling
    "outsider": ("init_dg", "init_elders"),
    "partner_member": ("initiatief", "init_dg", "init_elders"),
    "platform_admin": (),
}


@pytest.mark.parametrize("who", sorted(SEES_INITIATIEVEN))
async def test_who_sees_which_initiatief(rw, who):
    universe = _ids(rw, *INITIATIEVEN)
    async with client_as(rw.db, rw.person[who]) as c:
        listed = await _listed(c, "/api/initiatieven", universe)
    assert listed == _ids(rw, *SEES_INITIATIEVEN[who])


async def test_whoever_writes_an_initiatief_sees_it(rw):
    for who, person in rw.person.items():
        ctx = await build_permission_context(rw.db, person)
        async with client_as(rw.db, person) as c:
            visible = await _readable(
                c, "/api/initiatieven/{}", _ids(rw, *INITIATIEVEN)
            )
        for key in INITIATIEVEN:
            if await can(rw.db, ctx, "initiatief:update", "initiatief", rw.res[key]):
                assert rw.res[key] in visible, (who, key)


async def test_by_eenheid_lists_only_visible_initiatieven(rw):
    path = f"/api/initiatieven/by-eenheid/{rw.org['afdeling'].id}"
    async with client_as(rw.db, rw.person["dg_member"]) as c:
        hidden = await c.get(path)
    async with client_as(rw.db, rw.person["team_editor"]) as c:
        shown = await c.get(path)
    assert hidden.json() == []
    assert [i["initiatief_id"] for i in shown.json()] == [str(rw.res["initiatief"])]


async def test_access_level_viewer_follows_visibility(rw):
    url = f"/api/initiatieven/{rw.res['init_dg']}"
    async with client_as(rw.db, rw.person["viewer"]) as c:
        resp = await c.get(url)
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_level"] == "viewer"


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


async def test_lead_list_equals_detail_for_everyone(rw):
    universe = _ids(rw, *LEADS)
    for who, person in rw.person.items():
        async with client_as(rw.db, person) as c:
            listed = await _listed(c, "/api/leads", universe)
            readable = await _readable(c, "/api/leads/{}", universe)
            channels = await _readable(c, "/api/leads/{}/mattermost-channels", universe)
        assert listed == readable == channels, who


SEES_LEADS = {
    # lead_free has no initiatief: every logged-in user sees it
    "outsider": ("lead_free", "lead_elders", "lead_dg"),
    "lead_contact": ("lead_free", "lead_elders"),  # contactpersoon role only
    "dg_member": ("lead_free", "lead_dg"),
    # the team holds a role on the personal initiatief's lead
    "viewer": ("lead", "lead_free", "lead_dg", "lead_personal"),
    # writes the afdeling's lead without seeing its initiatief
    "lead_owner": ("lead", "lead_free"),
}


@pytest.mark.parametrize("who", sorted(SEES_LEADS))
async def test_lead_roles_make_a_lead_visible(rw, who):
    async with client_as(rw.db, rw.person[who]) as c:
        listed = await _listed(c, "/api/leads", _ids(rw, *LEADS))
    assert listed == _ids(rw, *SEES_LEADS[who])


async def test_whoever_writes_a_lead_sees_it(rw):
    for who, person in rw.person.items():
        ctx = await build_permission_context(rw.db, person)
        async with client_as(rw.db, person) as c:
            visible = await _readable(c, "/api/leads/{}", _ids(rw, *LEADS))
        for key in LEADS:
            if await can(rw.db, ctx, "lead:update", "lead", rw.res[key]):
                assert rw.res[key] in visible, (who, key)


async def test_search_finds_leads_by_the_same_rule(rw):
    async with client_as(rw.db, rw.person["outsider"]) as c:
        resp = await c.get("/api/search", params={"q": "Lead", "result_types": "lead"})
    assert resp.status_code == 200, resp.text
    found = {uuid.UUID(r["id"]) for r in resp.json()["results"]} & _ids(rw, *LEADS)
    assert found == _ids(rw, *SEES_LEADS["outsider"])


# ---------------------------------------------------------------------------
# authz answers reads with the same visibility
# ---------------------------------------------------------------------------

# (resource type, read permission, detail route, resource keys)
READ_TYPES = [
    (
        "corpus_node",
        "node:read",
        "/api/nodes/{}",
        (
            "node_directie",
            "node_afdeling",
            "node_team",
            "node_elders",
            "node_free",
            "node_sibling",
        ),
    ),
    ("task", "task:read", "/api/tasks/{}", ("task_team", "task_on_team_node")),
    (
        "edge",
        "edge:read",
        "/api/edges/{}",
        ("edge_team_directie", "edge_directie_elders"),
    ),
    (
        "opdracht",
        "opdracht:read",
        "/api/opdrachten/{}",
        ("opdracht_free", "opdracht_directie"),
    ),
    ("initiatief", "initiatief:read", "/api/initiatieven/{}", INITIATIEVEN),
    ("lead", "lead:read", "/api/leads/{}", LEADS),
]


@pytest.mark.parametrize(
    ("resource_type", "permission", "route", "keys"),
    READ_TYPES,
    ids=[t[0] for t in READ_TYPES],
)
async def test_can_read_equals_detail_for_everyone(
    rw, resource_type, permission, route, keys
):
    """``can(<type>:read)`` is visibility, so buttons and pages agree."""
    for who, person in rw.person.items():
        ctx = await build_permission_context(rw.db, person)
        async with client_as(rw.db, person) as c:
            for key in keys:
                resp = await c.get(route.format(rw.res[key]))
                decided = await can(rw.db, ctx, permission, resource_type, rw.res[key])
                assert decided is (resp.status_code == 200), (who, key, resp.text)


async def test_sub_records_read_through_their_parent(rw):
    for who, person in rw.person.items():
        ctx = await build_permission_context(rw.db, person)
        column = await can(
            rw.db, ctx, "lead_column:read", "lead_column", rw.res["lead_column"]
        )
        parent = await can(
            rw.db, ctx, "initiatief:read", "initiatief", rw.res["initiatief"]
        )
        assert column is parent, who


# ---------------------------------------------------------------------------
# LLM: kompas guidance and corpus gaps see what GET /nodes sees
# ---------------------------------------------------------------------------


class _FakeLLM:
    def __init__(self):
        self.prompted: list[str] = []

    async def score_edge_relevance(self, *, target_title, **_):
        self.prompted.append(target_title)
        return EdgeRelevanceResult(
            score=0.9, suggested_edge_type="verwijst_naar", reason="past"
        )


async def test_kompas_guidance_only_suggests_visible_nodes(rw):
    db = rw.db
    hidden = CorpusNode(
        id=uuid.uuid4(),
        title="Geheim instrument elders",
        node_type="instrument",
        status="actief",
        organisatie_eenheid_id=rw.org["elders"].id,
    )
    shown = CorpusNode(
        id=uuid.uuid4(),
        title="Instrument van het team",
        node_type="instrument",
        status="actief",
        organisatie_eenheid_id=rw.org["team"].id,
    )
    db.add_all([hidden, shown])
    await db.flush()

    fake = _FakeLLM()

    async def _llm_for(*_a, **_k):
        return fake

    body = {
        "dossier_id": str(rw.res["node_team"]),
        "step_node_types": ["instrument"],
        "max_candidates": 50,
    }
    with patch("bouwmeester.api.routes.llm.get_llm_service_for", _llm_for):
        async with client_as(db, rw.person["viewer"]) as c:
            resp = await c.post("/api/llm/kompas-guidance", json=body)
    assert resp.status_code == 200, resp.text
    titles = {s["target_node_title"] for s in resp.json()["suggestions"]}
    assert "Instrument van het team" in titles
    assert "Geheim instrument elders" not in titles
    assert "Geheim instrument elders" not in fake.prompted


async def test_corpus_gaps_list_only_visible_dossiers(rw):
    async with client_as(rw.db, rw.person["viewer"]) as c:
        viewer = await c.get("/api/llm/corpus-gaps")
    async with client_as(rw.db, rw.person["super_admin"]) as c:
        admin = await c.get("/api/llm/corpus-gaps")
    assert viewer.status_code == 200, viewer.text
    seen = {i["dossier_id"] for i in viewer.json()["items"]}
    all_ = {i["dossier_id"] for i in admin.json()["items"]}
    assert str(rw.res["node_team"]) in seen
    assert str(rw.res["node_elders"]) in all_
    assert str(rw.res["node_elders"]) not in seen
