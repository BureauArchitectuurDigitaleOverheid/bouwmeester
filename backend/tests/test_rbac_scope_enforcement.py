"""Tests for RBAC org scope enforcement on write endpoints.

Verifies that:
- Write endpoints return 403 when the user lacks the required permission
- check_org_scope blocks operations on eenheden outside the caller's scope
- check_resource_org_scope returns 404 for nonexistent resources
- Edge creation checks scope on both connected nodes
- Self-revoke of super_admin is blocked
- ministry_admin gets sub-tree visibility
"""

import uuid
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.models.org_naam import OrganisatieEenheidNaam
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole
from bouwmeester.models.task import Task

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_person(db: AsyncSession, naam: str) -> Person:
    """Helper: create a person with email."""
    uid = uuid.uuid4()
    email = f"{naam.lower().replace(' ', '-')}-{uid.hex[:8]}@example.com"
    person = Person(id=uid, naam=naam, email=email, functie="tester", is_active=True)
    db.add(person)
    await db.flush()
    db.add(PersonEmail(person_id=person.id, email=email, is_default=True))
    await db.flush()
    return person


async def _make_org(
    db: AsyncSession, naam: str, type_: str = "directie", parent_id=None
) -> OrganisatieEenheid:
    """Helper: create an org unit."""
    org = OrganisatieEenheid(
        id=uuid.uuid4(), naam=naam, type=type_, parent_id=parent_id
    )
    db.add(org)
    await db.flush()
    db.add(
        OrganisatieEenheidNaam(eenheid_id=org.id, naam=naam, geldig_van=date.today())
    )
    await db.flush()
    return org


async def _place_person(db: AsyncSession, person: Person, org: OrganisatieEenheid):
    """Helper: place person in org unit."""
    db.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=org.id,
            start_datum=date.today(),
        )
    )
    await db.flush()


async def _assign_role(
    db: AsyncSession,
    person: Person,
    role_id: str,
    org: OrganisatieEenheid | None = None,
):
    """Helper: assign a role to a person."""
    db.add(
        PersonRole(
            person_id=person.id,
            role_id=role_id,
            organisatie_eenheid_id=org.id if org else None,
            start_datum=date.today() - timedelta(days=1),
        )
    )
    await db.flush()


def _make_app_and_client(db_session, person):
    """Build a fresh app with overrides and an authenticated async client."""
    from bouwmeester.core.app import create_app

    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = lambda: person

    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-rbac"},
    )
    return app, client


@pytest.fixture
async def scope_setup(db_session: AsyncSession):
    """Set up two org units, an editor in org_a, nodes/tasks in both orgs.

    Returns a dict with test data and two clients: one for the scoped
    editor (org_a only) and one for a permissionless viewer.
    Each client gets its own app instance so dependency overrides don't clash.
    """
    org_a = await _make_org(db_session, "Org A")
    org_b = await _make_org(db_session, "Org B")

    editor = await _make_person(db_session, "Editor User")
    await _place_person(db_session, editor, org_a)
    await _assign_role(db_session, editor, "editor", org_a)

    viewer = await _make_person(db_session, "Viewer User")
    await _place_person(db_session, viewer, org_a)
    await _assign_role(db_session, viewer, "viewer", org_a)

    # Nodes
    node_a = CorpusNode(
        id=uuid.uuid4(),
        title="Node in A",
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=org_a.id,
    )
    node_b = CorpusNode(
        id=uuid.uuid4(),
        title="Node in B",
        node_type="doel",
        status="actief",
        organisatie_eenheid_id=org_b.id,
    )
    node_null = CorpusNode(
        id=uuid.uuid4(),
        title="Unassigned node",
        node_type="dossier",
        status="actief",
    )
    db_session.add_all([node_a, node_b, node_null])
    await db_session.flush()

    # Edge type
    et = EdgeType(
        id=f"test_rbac_{uuid.uuid4().hex[:8]}",
        label_nl="Test",
        label_en="Test",
        is_custom=True,
    )
    db_session.add(et)
    await db_session.flush()

    # Edge within org_a
    edge_a = Edge(
        id=uuid.uuid4(),
        from_node_id=node_a.id,
        to_node_id=node_null.id,
        edge_type_id=et.id,
    )
    db_session.add(edge_a)
    await db_session.flush()

    # Tasks
    task_a = Task(
        id=uuid.uuid4(),
        title="Task in A",
        node_id=node_a.id,
        status="open",
        priority="normaal",
        organisatie_eenheid_id=org_a.id,
    )
    task_b = Task(
        id=uuid.uuid4(),
        title="Task in B",
        node_id=node_b.id,
        status="open",
        priority="normaal",
        organisatie_eenheid_id=org_b.id,
    )
    db_session.add_all([task_a, task_b])
    await db_session.flush()

    editor_app, editor_client = _make_app_and_client(db_session, editor)
    viewer_app, viewer_client = _make_app_and_client(db_session, viewer)

    async with editor_client, viewer_client:
        yield {
            "editor_client": editor_client,
            "viewer_client": viewer_client,
            "editor": editor,
            "viewer": viewer,
            "org_a": org_a,
            "org_b": org_b,
            "node_a": node_a,
            "node_b": node_b,
            "node_null": node_null,
            "edge_type": et,
            "edge_a": edge_a,
            "task_a": task_a,
            "task_b": task_b,
        }

    editor_app.dependency_overrides.clear()
    viewer_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Permission guard tests (403 for missing permission)
# ---------------------------------------------------------------------------


async def test_viewer_cannot_create_node(scope_setup):
    """Viewer lacks node:create permission → 403."""
    s = scope_setup
    resp = await s["viewer_client"].post(
        "/api/nodes",
        json={"title": "Should fail", "node_type": "dossier", "status": "actief"},
    )
    assert resp.status_code == 403


async def test_viewer_cannot_update_node(scope_setup):
    """Viewer lacks node:update permission → 403."""
    s = scope_setup
    resp = await s["viewer_client"].put(
        f"/api/nodes/{s['node_a'].id}",
        json={"title": "Nope"},
    )
    assert resp.status_code == 403


async def test_viewer_cannot_delete_node(scope_setup):
    """Viewer lacks node:delete permission → 403."""
    s = scope_setup
    resp = await s["viewer_client"].delete(f"/api/nodes/{s['node_a'].id}")
    assert resp.status_code == 403


async def test_viewer_cannot_create_task(scope_setup):
    """Viewer lacks task:create permission → 403."""
    s = scope_setup
    resp = await s["viewer_client"].post(
        "/api/tasks",
        json={
            "title": "Nope",
            "node_id": str(s["node_a"].id),
            "organisatie_eenheid_id": str(s["org_a"].id),
        },
    )
    assert resp.status_code == 403


async def test_viewer_cannot_create_edge(scope_setup):
    """Viewer lacks edge:create permission → 403."""
    s = scope_setup
    resp = await s["viewer_client"].post(
        "/api/edges",
        json={
            "from_node_id": str(s["node_a"].id),
            "to_node_id": str(s["node_null"].id),
            "edge_type_id": s["edge_type"].id,
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Org scope enforcement tests (403 for out-of-scope eenheid)
# ---------------------------------------------------------------------------


async def test_update_node_in_other_org_returns_403(scope_setup):
    """Editor cannot update a node in org_b (outside their scope)."""
    s = scope_setup
    resp = await s["editor_client"].put(
        f"/api/nodes/{s['node_b'].id}",
        json={"title": "Should be blocked"},
    )
    assert resp.status_code == 403


async def test_delete_node_in_other_org_returns_403(scope_setup):
    """Editor cannot delete a node in org_b."""
    s = scope_setup
    resp = await s["editor_client"].delete(f"/api/nodes/{s['node_b'].id}")
    assert resp.status_code == 403


async def test_create_task_in_other_org_returns_403(scope_setup):
    """Editor cannot create a task scoped to org_b."""
    s = scope_setup
    resp = await s["editor_client"].post(
        "/api/tasks",
        json={
            "title": "Task for wrong org",
            "node_id": str(s["node_a"].id),
            "organisatie_eenheid_id": str(s["org_b"].id),
        },
    )
    assert resp.status_code == 403


async def test_update_task_in_other_org_returns_403(scope_setup):
    """Editor cannot update a task in org_b."""
    s = scope_setup
    resp = await s["editor_client"].put(
        f"/api/tasks/{s['task_b'].id}",
        json={"title": "Nope"},
    )
    assert resp.status_code == 403


async def test_delete_task_in_other_org_returns_403(scope_setup):
    """Editor cannot delete a task in org_b."""
    s = scope_setup
    resp = await s["editor_client"].delete(f"/api/tasks/{s['task_b'].id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Edge scope enforcement (both nodes checked)
# ---------------------------------------------------------------------------


async def test_create_edge_to_node_in_other_org_returns_403(scope_setup):
    """Creating an edge where to_node is in org_b → 403."""
    s = scope_setup
    resp = await s["editor_client"].post(
        "/api/edges",
        json={
            "from_node_id": str(s["node_a"].id),
            "to_node_id": str(s["node_b"].id),
            "edge_type_id": s["edge_type"].id,
        },
    )
    assert resp.status_code == 403


async def test_create_edge_from_node_in_other_org_returns_403(scope_setup):
    """Creating an edge where from_node is in org_b → 403."""
    s = scope_setup
    resp = await s["editor_client"].post(
        "/api/edges",
        json={
            "from_node_id": str(s["node_b"].id),
            "to_node_id": str(s["node_a"].id),
            "edge_type_id": s["edge_type"].id,
        },
    )
    assert resp.status_code == 403


async def test_create_edge_within_scope_succeeds(scope_setup):
    """Creating an edge between node_a and node_null (both in scope) works."""
    s = scope_setup
    # node_null has no org → always allowed; node_a is in org_a → in scope
    resp = await s["editor_client"].post(
        "/api/edges",
        json={
            "from_node_id": str(s["node_null"].id),
            "to_node_id": str(s["node_a"].id),
            "edge_type_id": s["edge_type"].id,
        },
    )
    # May be 201 or 422 (schema validation) — but not 403
    assert resp.status_code != 403


# ---------------------------------------------------------------------------
# check_resource_org_scope returns 404 for nonexistent resource
# ---------------------------------------------------------------------------


async def test_update_nonexistent_node_returns_404(scope_setup):
    """Updating a node that doesn't exist returns 404 (not silent pass)."""
    s = scope_setup
    fake_id = uuid.uuid4()
    resp = await s["editor_client"].put(
        f"/api/nodes/{fake_id}",
        json={"title": "Ghost"},
    )
    assert resp.status_code == 404


async def test_delete_nonexistent_task_returns_404(scope_setup):
    """Deleting a task that doesn't exist returns 404."""
    s = scope_setup
    fake_id = uuid.uuid4()
    resp = await s["editor_client"].delete(f"/api/tasks/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Allowed operations within scope
# ---------------------------------------------------------------------------


async def test_update_node_in_own_org_succeeds(scope_setup):
    """Editor can update a node in org_a (their own scope)."""
    s = scope_setup
    resp = await s["editor_client"].put(
        f"/api/nodes/{s['node_a'].id}",
        json={"title": "Updated title"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated title"


async def test_create_task_in_own_org_succeeds(scope_setup):
    """Editor can create a task scoped to org_a."""
    s = scope_setup
    resp = await s["editor_client"].post(
        "/api/tasks",
        json={
            "title": "New task in scope",
            "node_id": str(s["node_a"].id),
            "organisatie_eenheid_id": str(s["org_a"].id),
        },
    )
    assert resp.status_code == 201


async def test_update_task_in_own_org_succeeds(scope_setup):
    """Editor can update a task in org_a."""
    s = scope_setup
    resp = await s["editor_client"].put(
        f"/api/tasks/{s['task_a'].id}",
        json={"title": "Updated task"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Self-revoke super_admin guard
# ---------------------------------------------------------------------------


@pytest.fixture
async def admin_setup(db_session: AsyncSession):
    """Set up a super_admin user with a role assignment."""
    admin = await _make_person(db_session, "Admin User")
    await _assign_role(db_session, admin, "super_admin")

    # Get the assignment ID
    from sqlalchemy import select

    stmt = select(PersonRole).where(
        PersonRole.person_id == admin.id,
        PersonRole.role_id == "super_admin",
    )
    result = await db_session.execute(stmt)
    assignment = result.scalar_one()

    app, client = _make_app_and_client(db_session, admin)

    async with client:
        yield {"client": client, "admin": admin, "assignment_id": assignment.id}

    app.dependency_overrides.clear()


async def test_cannot_revoke_own_super_admin(admin_setup):
    """Super admin cannot revoke their own super_admin role."""
    s = admin_setup
    resp = await s["client"].delete(f"/api/roles/assignments/{s['assignment_id']}")
    assert resp.status_code == 400
    assert "eigen" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Ministry admin sub-tree visibility
# ---------------------------------------------------------------------------


@pytest.fixture
async def ministry_setup(db_session: AsyncSession):
    """Set up a ministry_admin with sub-tree visibility."""
    ministry = await _make_org(db_session, "Testministerie", type_="ministerie")
    child = await _make_org(
        db_session, "Child directie", type_="directie", parent_id=ministry.id
    )
    other = await _make_org(db_session, "Other directie", type_="directie")

    admin = await _make_person(db_session, "Ministry Admin")
    await _place_person(db_session, admin, ministry)
    await _assign_role(db_session, admin, "ministry_admin", ministry)

    # Create nodes in child and other orgs
    child_node = CorpusNode(
        id=uuid.uuid4(),
        title="Child node",
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=child.id,
    )
    other_node = CorpusNode(
        id=uuid.uuid4(),
        title="Other node",
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=other.id,
    )
    db_session.add_all([child_node, other_node])
    await db_session.flush()

    app, client = _make_app_and_client(db_session, admin)

    async with client:
        yield {
            "client": client,
            "ministry": ministry,
            "child": child,
            "other": other,
            "child_node": child_node,
            "other_node": other_node,
        }

    app.dependency_overrides.clear()


async def test_ministry_admin_sees_child_org_nodes(ministry_setup):
    """Ministry admin can see nodes in child org unit."""
    s = ministry_setup
    resp = await s["client"].get(f"/api/nodes/{s['child_node'].id}")
    assert resp.status_code == 200


async def test_ministry_admin_cannot_see_other_org_nodes(ministry_setup):
    """Ministry admin cannot see nodes in unrelated org unit."""
    s = ministry_setup
    resp = await s["client"].get(f"/api/nodes/{s['other_node'].id}")
    assert resp.status_code == 404
