"""Authorization tests for the parlementair router.

Verifies that an authenticated non-admin user without the
``parlementair:read`` / ``parlementair:review`` / ``parlementair:import``
permissions cannot access the corresponding endpoints.

The dev-mode super-admin shortcut (no OIDC) is bypassed by overriding
``get_optional_user`` and ``get_permission_context`` directly on the app.
"""

import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.resource_permission import ResourcePermission
from tests.authz_world import World, add_directie_admin, ask, make_item
from tests.factories import client_as


@pytest.fixture
def _test_app():
    from bouwmeester.core.app import create_app

    return create_app()


def _make_client(app, db_session, person, perms: set[str]):
    """Build a client where the user has exactly *perms* (and nothing else)."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = lambda: person
    app.dependency_overrides[get_permission_context] = lambda: PermissionContext(
        person_id=person.id,
        is_authenticated=True,
        effective_permissions=set(perms),
    )

    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-parlementair-authz"},
    )


@pytest.fixture
async def parlementair_authz_setup(db_session: AsyncSession, _test_app):
    person = Person(
        id=uuid.uuid4(),
        naam="Parlementair Tester",
        email=f"parl-{uuid.uuid4().hex[:8]}@example.com",
        functie="tester",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEmail(person_id=person.id, email=person.email, is_default=True)
    )
    await db_session.flush()

    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-99",
        titel="Authz testmotie",
        onderwerp="Authz",
        bron="tweede_kamer",
        datum=date(2024, 6, 15),
        status="pending",
    )
    db_session.add(item)
    await db_session.flush()

    yield {"app": _test_app, "person": person, "item": item}

    _test_app.dependency_overrides.clear()


async def test_list_imports_requires_parlementair_read(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user without parlementair:read gets 403 on GET /imports."""
    s = parlementair_authz_setup
    async with _make_client(s["app"], db_session, s["person"], set()) as ac:
        resp = await ac.get("/api/parlementair/imports")
    assert resp.status_code == 403


async def test_list_imports_allows_parlementair_read(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user with parlementair:read sees the imports list."""
    s = parlementair_authz_setup

    async def _override_get_db():
        yield db_session

    s["app"].dependency_overrides[get_db] = _override_get_db

    async with _make_client(
        s["app"], db_session, s["person"], {"parlementair:read"}
    ) as ac:
        resp = await ac.get("/api/parlementair/imports")
    assert resp.status_code == 200
    ids = {x["id"] for x in resp.json()}
    assert str(s["item"].id) in ids


async def test_trigger_import_requires_parlementair_import(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user with only parlementair:read cannot trigger an import."""
    s = parlementair_authz_setup

    async def _override_get_db():
        yield db_session

    s["app"].dependency_overrides[get_db] = _override_get_db

    async with _make_client(
        s["app"], db_session, s["person"], {"parlementair:read"}
    ) as ac:
        resp = await ac.post("/api/parlementair/imports/trigger")
    assert resp.status_code == 403


async def test_reject_import_requires_parlementair_review(
    parlementair_authz_setup, db_session: AsyncSession
):
    """A user with only parlementair:read cannot reject an import."""
    s = parlementair_authz_setup

    async def _override_get_db():
        yield db_session

    s["app"].dependency_overrides[get_db] = _override_get_db

    async with _make_client(
        s["app"], db_session, s["person"], {"parlementair:read"}
    ) as ac:
        resp = await ac.put(f"/api/parlementair/imports/{s['item'].id}/reject")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Real permission resolution (``world`` from tests/authz_world.py)
# ---------------------------------------------------------------------------


async def _review_item(w: World, *targets: str) -> ParlementairItem:
    """An imported item on a fresh node without eenheid, with suggestions."""
    node = CorpusNode(
        id=uuid.uuid4(), title="Motie", node_type="politieke_input", status="actief"
    )
    edge_type = EdgeType(id=f"parl_{uuid.uuid4().hex[:8]}", label_nl="T", label_en="T")
    w.db.add_all([node, edge_type])
    await w.db.flush()
    item = ParlementairItem(
        id=uuid.uuid4(),
        type="motie",
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-1",
        titel="Motie",
        onderwerp="Motie",
        bron="tweede_kamer",
        status="imported",
        corpus_node_id=node.id,
    )
    w.db.add(item)
    await w.db.flush()
    for target in targets:
        w.db.add(
            SuggestedEdge(
                parlementair_item_id=item.id,
                target_node_id=w.res[target],
                edge_type_id=edge_type.id,
                confidence=0.9,
            )
        )
    await w.db.flush()
    return item


async def _owners(w: World, node_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await w.db.scalars(
        select(ResourcePermission.person_id).where(
            ResourcePermission.resource_type == "corpus_node",
            ResourcePermission.resource_id == node_id,
            ResourcePermission.rol == "eigenaar",
        )
    )
    return set(rows)


def _complete(w: World, who: str) -> dict:
    return {"eigenaar_id": str(w.person[who].id), "tasks": []}


# Naming the first eigenaar while completing a review:
# (reviewer, item node, named eigenaar, expected status).
FIRST_OWNER_CASES = [
    # the review names someone else who can read the node
    ("team_editor", "node_team", "viewer", 200),
    ("ministry_admin", "node_directie", "manager", 200),
    # a resource role is enough to read the node
    ("manager", "node_directie", "role_only", 200),
    # someone who cannot read the node would receive node:delete on it
    ("team_editor", "node_team", "role_only", 403),
    # naming yourself only when you already edit the node
    ("team_editor", "node_team", "team_editor", 200),
    ("ministry_admin", "node_directie", "ministry_admin", 403),
]


@pytest.mark.parametrize(
    ("who", "node", "eigenaar", "expected"),
    FIRST_OWNER_CASES,
    ids=[f"{c[0]}-{c[2]}" for c in FIRST_OWNER_CASES],
)
async def test_review_names_the_first_eigenaar(
    world: World, who: str, node: str, eigenaar: str, expected: int
):
    """The route and ``parlementair:name_owner`` decide alike."""
    await add_directie_admin(world, "ministry_admin", "Ministeriebeheerder")
    item = await make_item(world, node)
    target = world.person[eigenaar]
    async with client_as(world.db, world.person[who]) as c:
        asked = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask(
                        "parlementair:name_owner",
                        "corpus_node",
                        item.corpus_node_id,
                        target_person_id=target.id,
                    )
                ]
            },
        )
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json={"eigenaar_id": str(target.id), "tasks": []},
        )
    assert asked.json()["evaluations"][0]["decision"] is (expected == 200)
    assert resp.status_code == expected, resp.text
    named = {target.id} if expected == 200 else set()
    assert await _owners(world, item.corpus_node_id) == named


# Replacing the current eigenaars while completing a review:
# (reviewer, current eigenaars, expected status).
REPLACE_OWNER_CASES = [
    # an editor holds no node:delete, so cannot hand out eigenaar
    ("team_editor", ("afd_editor",), 403),
    # two eigenaars used to crash the review with a 500
    ("manager", ("team_editor", "afd_editor"), 200),
]


@pytest.mark.parametrize(("who", "owners", "expected"), REPLACE_OWNER_CASES)
async def test_review_replaces_the_eigenaars(
    world: World, who: str, owners: tuple[str, ...], expected: int
):
    """The route and ``parlementair:name_owner`` decide alike."""
    item = await _review_item(world)
    for owner in owners:
        world.db.add(
            ResourcePermission(
                person_id=world.person[owner].id,
                resource_type="corpus_node",
                resource_id=item.corpus_node_id,
                rol="eigenaar",
            )
        )
    await world.db.flush()
    viewer = world.person["viewer"]
    async with client_as(world.db, world.person[who]) as c:
        asked = await c.post(
            "/api/authz/evaluations",
            json={
                "evaluations": [
                    ask(
                        "parlementair:name_owner",
                        "corpus_node",
                        item.corpus_node_id,
                        target_person_id=viewer.id,
                    )
                ]
            },
        )
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json=_complete(world, "viewer"),
        )
    assert asked.json()["evaluations"][0]["decision"] is (expected == 200)
    assert resp.status_code == expected, resp.text
    kept = {world.person[o].id for o in owners}
    assert await _owners(world, item.corpus_node_id) == (
        {viewer.id} if expected == 200 else kept
    )


async def test_suggestions_hide_target_nodes_the_reader_cannot_see(world: World):
    item = await _review_item(world, "node_team", "node_elders")
    async with client_as(world.db, world.person["viewer"]) as c:
        detail = await c.get(f"/api/parlementair/imports/{item.id}")
        listed = await c.get("/api/parlementair/imports")
        queue = await c.get("/api/parlementair/review-queue")
    assert detail.status_code == 200, detail.text
    for body in (
        detail.json(),
        next(x for x in listed.json() if x["id"] == str(item.id)),
        next(x for x in queue.json() if x["id"] == str(item.id)),
    ):
        targets = {e["target_node_id"] for e in body["suggested_edges"]}
        assert targets == {str(world.res["node_team"])}


async def test_suggestions_show_targets_read_through_a_resource_role(world: World):
    """A target node is shown by the node:read rule, not by its eenheid only."""
    item = await _review_item(world, "node_team", "node_elders")
    world.db.add(
        ResourcePermission(
            person_id=world.person["viewer"].id,
            resource_type="corpus_node",
            resource_id=world.res["node_elders"],
            rol="betrokken",
        )
    )
    await world.db.flush()
    async with client_as(world.db, world.person["viewer"]) as c:
        detail = await c.get(f"/api/parlementair/imports/{item.id}")
    targets = {e["target_node_id"] for e in detail.json()["suggested_edges"]}
    assert targets == {str(world.res["node_team"]), str(world.res["node_elders"])}


async def test_suggestions_show_every_target_to_super_admin(world: World):
    item = await _review_item(world, "node_team", "node_elders")
    async with client_as(world.db, world.person["super_admin"]) as c:
        resp = await c.get(f"/api/parlementair/imports/{item.id}")
    assert len(resp.json()["suggested_edges"]) == 2


async def test_reset_without_review_right_keeps_the_edge(world: World):
    item = await _review_item(world, "node_team")
    suggestion = await world.db.scalar(
        select(SuggestedEdge).where(SuggestedEdge.parlementair_item_id == item.id)
    )
    async with client_as(world.db, world.person["manager"]) as c:
        approved = await c.put(f"/api/parlementair/edges/{suggestion.id}/approve")
    assert approved.status_code == 200, approved.text
    edge_id = approved.json()["edge_id"]
    async with client_as(world.db, world.person["viewer"]) as c:
        resp = await c.put(f"/api/parlementair/edges/{suggestion.id}/reset")
    assert resp.status_code == 403
    assert await world.db.get(Edge, uuid.UUID(edge_id)) is not None


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("patch", "", {"edge_type_id": "x"}),
        ("put", "/approve", None),
        ("put", "/reject", None),
        ("put", "/reset", None),
    ],
)
async def test_suggested_edge_review_is_decided_on_the_suggestion(
    world: World, method: str, path: str, json: dict | None
):
    """Every review route asks authz on the suggestion: 403 without, 404 unknown."""
    item = await _review_item(world, "node_team")
    suggestion = await world.db.scalar(
        select(SuggestedEdge).where(SuggestedEdge.parlementair_item_id == item.id)
    )
    kwargs = {"json": json} if json is not None else {}
    async with client_as(world.db, world.person["viewer"]) as c:
        refused = await c.request(
            method, f"/api/parlementair/edges/{suggestion.id}{path}", **kwargs
        )
    async with client_as(world.db, world.person["manager"]) as c:
        missing = await c.request(
            method, f"/api/parlementair/edges/{uuid.uuid4()}{path}", **kwargs
        )
    assert refused.status_code == 403, refused.text
    assert missing.status_code == 404, missing.text
    await world.db.refresh(suggestion)
    assert suggestion.status == "pending"
