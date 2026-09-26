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
from tests.authz_world import World, add_directie_admin
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


async def test_editor_reviewer_names_first_eigenaar(world: World):
    """Naming the first eigenaar is the review itself, not a grant."""
    item = await _review_item(world)
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json=_complete(world, "viewer"),
        )
    assert resp.status_code == 200, resp.text
    assert await _owners(world, item.corpus_node_id) == {world.person["viewer"].id}


async def test_reviewer_who_edits_the_node_names_self_eigenaar(world: World):
    """Claiming a node you already edit hands you nothing you lacked."""
    item = await _review_item(world)
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json=_complete(world, "team_editor"),
        )
    assert resp.status_code == 200, resp.text
    assert await _owners(world, item.corpus_node_id) == {world.person["team_editor"].id}


async def test_reviewer_without_node_update_cannot_name_self_eigenaar(world: World):
    """A ministry_admin reviews but does not edit nodes: no self-grant."""
    await add_directie_admin(world, "org_admin", "Directiebeheerder")
    own, other = await _review_item(world), await _review_item(world)
    async with client_as(world.db, world.person["org_admin"]) as c:
        named_self = await c.post(
            f"/api/parlementair/imports/{own.id}/complete",
            json=_complete(world, "org_admin"),
        )
        named_other = await c.post(
            f"/api/parlementair/imports/{other.id}/complete",
            json=_complete(world, "viewer"),
        )
    assert named_self.status_code == 403, named_self.text
    assert await _owners(world, own.corpus_node_id) == set()
    assert named_other.status_code == 200, named_other.text


async def test_reviewer_cannot_replace_eigenaar_without_grant_authority(world: World):
    """Replacing an eigenaar needs node:delete, which an editor lacks."""
    item = await _review_item(world)
    world.db.add(
        ResourcePermission(
            person_id=world.person["afd_editor"].id,
            resource_type="corpus_node",
            resource_id=item.corpus_node_id,
            rol="eigenaar",
        )
    )
    await world.db.flush()
    async with client_as(world.db, world.person["team_editor"]) as c:
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json=_complete(world, "viewer"),
        )
    assert resp.status_code == 403
    assert await _owners(world, item.corpus_node_id) == {world.person["afd_editor"].id}


async def test_review_replaces_several_eigenaars(world: World):
    """Two eigenaars used to crash the review with a 500."""
    item = await _review_item(world)
    for who in ("team_editor", "afd_editor"):
        world.db.add(
            ResourcePermission(
                person_id=world.person[who].id,
                resource_type="corpus_node",
                resource_id=item.corpus_node_id,
                rol="eigenaar",
            )
        )
    await world.db.flush()
    async with client_as(world.db, world.person["manager"]) as c:
        resp = await c.post(
            f"/api/parlementair/imports/{item.id}/complete",
            json=_complete(world, "viewer"),
        )
    assert resp.status_code == 200, resp.text
    assert await _owners(world, item.corpus_node_id) == {world.person["viewer"].id}


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
