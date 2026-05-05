"""Tests for org-based visibility filtering across API routes.

Verifies that non-admin users only see data belonging to their own
organisatie-eenheden (or data without an org assignment).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.task import Task

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _test_app():
    from bouwmeester.core.app import create_app

    return create_app()


@pytest.fixture
async def org_visibility_setup(db_session: AsyncSession, _test_app):
    """Set up a non-admin user with org visibility and test data.

    Creates:
    - A non-admin person placed in ``visible_org``
    - ``visible_org`` and ``invisible_org`` org units
    - Nodes, tasks in both orgs (plus one with no org)
    - Edges between visible and invisible nodes
    - An authenticated HTTPX client for this user
    """
    # Create two org units
    visible_org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Zichtbaar",
        type="directie",
    )
    invisible_org = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="Onzichtbaar",
        type="directie",
    )
    db_session.add_all([visible_org, invisible_org])
    await db_session.flush()

    # Create person
    person = Person(
        id=uuid.uuid4(),
        naam="Org Test User",
        email=f"orgtest-{uuid.uuid4().hex[:8]}@example.com",
        functie="tester",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEmail(person_id=person.id, email=person.email, is_default=True)
    )

    # Place person in visible_org
    db_session.add(
        PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=visible_org.id,
            start_datum=date.today(),
        )
    )
    await db_session.flush()

    # Create nodes: one in each org, one without org
    visible_node = CorpusNode(
        id=uuid.uuid4(),
        title="Zichtbaar dossier",
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=visible_org.id,
    )
    invisible_node = CorpusNode(
        id=uuid.uuid4(),
        title="Onzichtbaar dossier",
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=invisible_org.id,
    )
    unassigned_node = CorpusNode(
        id=uuid.uuid4(),
        title="Ongeplaatst dossier",
        node_type="dossier",
        status="actief",
        organisatie_eenheid_id=None,
    )
    db_session.add_all([visible_node, invisible_node, unassigned_node])
    await db_session.flush()

    # Create tasks
    visible_task = Task(
        id=uuid.uuid4(),
        title="Zichtbare taak",
        node_id=visible_node.id,
        status="open",
        priority="normaal",
        organisatie_eenheid_id=visible_org.id,
    )
    invisible_task = Task(
        id=uuid.uuid4(),
        title="Onzichtbare taak",
        node_id=invisible_node.id,
        status="open",
        priority="normaal",
        organisatie_eenheid_id=invisible_org.id,
    )
    db_session.add_all([visible_task, invisible_task])
    await db_session.flush()

    # Create opdrachten: one in each org, one without org
    visible_opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Zichtbare opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=visible_node.id,
        opdrachtgever_id=visible_org.id,
        budget=Decimal("100000"),
        gerealiseerd=Decimal("25000"),
    )
    invisible_opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Onzichtbare opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=invisible_node.id,
        opdrachtgever_id=invisible_org.id,
        budget=Decimal("200000"),
        gerealiseerd=Decimal("50000"),
    )
    unassigned_opdracht = Opdracht(
        id=uuid.uuid4(),
        titel="Ongeplaatste opdracht",
        type="opdracht",
        status="actief",
        begrotingsjaar=2025,
        instrument_id=unassigned_node.id,
        opdrachtgever_id=None,
        budget=Decimal("50000"),
        gerealiseerd=Decimal("0"),
    )
    db_session.add_all([visible_opdracht, invisible_opdracht, unassigned_opdracht])
    await db_session.flush()

    # Create edge type
    from bouwmeester.models.edge_type import EdgeType

    et = EdgeType(
        id=f"test_vis_{uuid.uuid4().hex[:8]}",
        label_nl="Test",
        label_en="Test",
        is_custom=True,
    )
    db_session.add(et)
    await db_session.flush()

    # Create edges
    edge_both_visible = Edge(
        id=uuid.uuid4(),
        from_node_id=visible_node.id,
        to_node_id=unassigned_node.id,
        edge_type_id=et.id,
    )
    edge_one_invisible = Edge(
        id=uuid.uuid4(),
        from_node_id=visible_node.id,
        to_node_id=invisible_node.id,
        edge_type_id=et.id,
    )
    db_session.add_all([edge_both_visible, edge_one_invisible])
    await db_session.flush()

    # Build authenticated client
    app = _test_app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = lambda: person

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-org-visibility"},
    ) as ac:
        yield {
            "client": ac,
            "person": person,
            "visible_org": visible_org,
            "invisible_org": invisible_org,
            "visible_node": visible_node,
            "invisible_node": invisible_node,
            "unassigned_node": unassigned_node,
            "visible_task": visible_task,
            "invisible_task": invisible_task,
            "edge_both_visible": edge_both_visible,
            "edge_one_invisible": edge_one_invisible,
            "visible_opdracht": visible_opdracht,
            "invisible_opdracht": invisible_opdracht,
            "unassigned_opdracht": unassigned_opdracht,
        }

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Node visibility tests
# ---------------------------------------------------------------------------


async def test_list_nodes_hides_invisible_org(org_visibility_setup):
    """Non-admin should not see nodes from an org they are not placed in."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/nodes")
    assert resp.status_code == 200
    node_ids = {n["id"] for n in resp.json()}
    assert str(s["visible_node"].id) in node_ids
    assert str(s["invisible_node"].id) not in node_ids


async def test_list_nodes_shows_null_org(org_visibility_setup):
    """Non-admin should see nodes with no org assignment (NULL)."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/nodes")
    assert resp.status_code == 200
    node_ids = {n["id"] for n in resp.json()}
    assert str(s["unassigned_node"].id) in node_ids


async def test_get_node_returns_404_for_invisible(org_visibility_setup):
    """Non-admin should get 404 for a node in an invisible org."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/nodes/{s['invisible_node'].id}")
    assert resp.status_code == 404


async def test_get_node_allows_visible(org_visibility_setup):
    """Non-admin should be able to get a node in their visible org."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/nodes/{s['visible_node'].id}")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Task visibility tests
# ---------------------------------------------------------------------------


async def test_list_tasks_hides_invisible_org(org_visibility_setup):
    """Non-admin should not see tasks from an invisible org."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/tasks")
    assert resp.status_code == 200
    task_ids = {t["id"] for t in resp.json()}
    assert str(s["visible_task"].id) in task_ids
    assert str(s["invisible_task"].id) not in task_ids


async def test_list_tasks_by_node_hides_invisible_org(org_visibility_setup):
    """Filtering tasks by node_id should still respect org visibility."""
    s = org_visibility_setup
    resp = await s["client"].get(
        "/api/tasks", params={"node_id": str(s["invisible_node"].id)}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


async def test_get_task_forbidden_for_invisible(org_visibility_setup):
    """GET /tasks/{id} returns 403 for a task in an invisible org."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/tasks/{s['invisible_task'].id}")
    assert resp.status_code == 403


async def test_get_task_subtasks_forbidden_for_invisible(org_visibility_setup):
    """GET /tasks/{id}/subtasks returns 403 for a parent in an invisible org."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/tasks/{s['invisible_task'].id}/subtasks")
    assert resp.status_code == 403


async def test_eenheid_overview_forbids_invisible_eenheid(org_visibility_setup):
    """GET /tasks/eenheid-overview rejects an invisible eenheid."""
    s = org_visibility_setup
    resp = await s["client"].get(
        "/api/tasks/eenheid-overview",
        params={"organisatie_eenheid_id": str(s["invisible_org"].id)},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Edge visibility tests
# ---------------------------------------------------------------------------


async def test_list_edges_hides_edge_to_invisible_node(org_visibility_setup):
    """Non-admin should not see an edge where one endpoint is invisible."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/edges")
    assert resp.status_code == 200
    edge_ids = {e["id"] for e in resp.json()}
    assert str(s["edge_one_invisible"].id) not in edge_ids


async def test_list_edges_shows_edge_between_visible_nodes(org_visibility_setup):
    """Non-admin should see an edge where both endpoints are visible."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/edges")
    assert resp.status_code == 200
    edge_ids = {e["id"] for e in resp.json()}
    assert str(s["edge_both_visible"].id) in edge_ids


async def test_get_edge_returns_404_for_invisible(org_visibility_setup):
    """Non-admin should get 404 for an edge touching an invisible node."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/edges/{s['edge_one_invisible'].id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Opdracht visibility tests
# ---------------------------------------------------------------------------


async def test_list_opdrachten_hides_invisible_org(org_visibility_setup):
    """Non-admin should not see opdrachten from an invisible org."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/opdrachten")
    assert resp.status_code == 200
    ids = {o["id"] for o in resp.json()}
    assert str(s["visible_opdracht"].id) in ids
    assert str(s["invisible_opdracht"].id) not in ids


async def test_list_opdrachten_shows_null_org(org_visibility_setup):
    """Non-admin should see opdrachten without opdrachtgever_id (NULL)."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/opdrachten")
    assert resp.status_code == 200
    ids = {o["id"] for o in resp.json()}
    assert str(s["unassigned_opdracht"].id) in ids


async def test_summary_excludes_invisible_org(org_visibility_setup):
    """Summary aggregates only over opdrachten the user can see."""
    s = org_visibility_setup
    resp = await s["client"].get("/api/opdrachten/summary")
    assert resp.status_code == 200
    data = resp.json()
    # visible (100k + 50k null) but not invisible (200k)
    assert int(data["count"]) == 2
    assert Decimal(str(data["totaal_budget"])) == Decimal("150000")
    assert Decimal(str(data["totaal_gerealiseerd"])) == Decimal("25000")


async def test_get_opdracht_forbidden_for_invisible(org_visibility_setup):
    """Non-admin should get 403 for an opdracht in an invisible org."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/opdrachten/{s['invisible_opdracht'].id}")
    assert resp.status_code == 403


async def test_get_opdracht_allows_visible(org_visibility_setup):
    """Non-admin should be able to read an opdracht in their org."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/opdrachten/{s['visible_opdracht'].id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(s["visible_opdracht"].id)


# ---------------------------------------------------------------------------
# Node-driven opdracht endpoints (instrument-detail leakage)
# ---------------------------------------------------------------------------


async def test_get_node_opdrachten_filters_invisible(org_visibility_setup):
    """GET /nodes/{instrument}/opdrachten only shows opdrachten in scope."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/nodes/{s['visible_node'].id}/opdrachten")
    assert resp.status_code == 200
    ids = {o["id"] for o in resp.json()}
    assert str(s["invisible_opdracht"].id) not in ids


async def test_get_node_opdrachten_forbids_invisible_node(org_visibility_setup):
    """An invisible node returns 403 via check_resource_org_scope."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/nodes/{s['invisible_node'].id}/opdrachten")
    assert resp.status_code == 403


async def test_get_node_financieel_forbids_invisible_node(org_visibility_setup):
    """Financial overview on an invisible node is forbidden."""
    s = org_visibility_setup
    resp = await s["client"].get(f"/api/nodes/{s['invisible_node'].id}/financieel")
    assert resp.status_code == 403
