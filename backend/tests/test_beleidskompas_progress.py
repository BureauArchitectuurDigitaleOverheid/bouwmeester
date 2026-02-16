"""Tests for beleidskompas progress computation."""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.edge_type import EdgeType
from bouwmeester.repositories.corpus_node import CorpusNodeRepository


@pytest.fixture
async def onderdeel_van_type(db_session):
    """Ensure the onderdeel_van edge type exists."""
    result = await db_session.execute(
        select(EdgeType).where(EdgeType.id == "onderdeel_van")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    et = EdgeType(
        id="onderdeel_van",
        label_nl="Onderdeel van",
        label_en="Part of",
        description="Onderdeel van relatie",
        is_custom=False,
    )
    db_session.add(et)
    await db_session.flush()
    return et


@pytest.fixture
async def dossier_node(db_session):
    """Create a dossier node."""
    node = CorpusNode(
        id=uuid.uuid4(),
        title="Test dossier",
        node_type="dossier",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()
    return node


@pytest.fixture
def make_child(db_session, onderdeel_van_type):
    """Factory to create a child node linked to a dossier via onderdeel_van."""

    async def _make(dossier, node_type: str, title: str = "Child") -> CorpusNode:
        child = CorpusNode(
            id=uuid.uuid4(),
            title=title,
            node_type=node_type,
            status="actief",
        )
        db_session.add(child)
        await db_session.flush()
        edge = Edge(
            id=uuid.uuid4(),
            from_node_id=child.id,
            to_node_id=dossier.id,
            edge_type_id="onderdeel_van",
        )
        db_session.add(edge)
        await db_session.flush()
        return child

    return _make


# ---------------------------------------------------------------------------
# Repository: get_beleidskompas_progress
# ---------------------------------------------------------------------------


async def test_progress_empty_input(db_session):
    """Empty dossier list returns empty dict."""
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([])
    assert result == {}


async def test_progress_dossier_no_children(db_session, dossier_node):
    """Dossier with no children returns 0/5."""
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (0, 5)


async def test_progress_single_step_complete(db_session, dossier_node, make_child):
    """Dossier with one probleem child → 1/5."""
    await make_child(dossier_node, "probleem")
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (1, 5)


async def test_progress_partial_multi_type_step(db_session, dossier_node, make_child):
    """Step 5 requires beleidskader + instrument + maatregel.

    Having only beleidskader should NOT count step 5 as complete.
    """
    await make_child(dossier_node, "beleidskader")
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (0, 5)


async def test_progress_partial_multi_type_two_of_three(
    db_session, dossier_node, make_child
):
    """Two of three types for step 5 → still incomplete."""
    await make_child(dossier_node, "beleidskader")
    await make_child(dossier_node, "instrument")
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (0, 5)


async def test_progress_multi_type_step_complete(db_session, dossier_node, make_child):
    """All three types for step 5 → step counts as complete."""
    await make_child(dossier_node, "beleidskader")
    await make_child(dossier_node, "instrument")
    await make_child(dossier_node, "maatregel")
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (1, 5)


async def test_progress_all_steps_complete(db_session, dossier_node, make_child):
    """Dossier with all 5 steps complete → 5/5."""
    await make_child(dossier_node, "probleem")
    await make_child(dossier_node, "doel")
    await make_child(dossier_node, "beleidsoptie")
    await make_child(dossier_node, "effect")
    await make_child(dossier_node, "beleidskader")
    await make_child(dossier_node, "instrument")
    await make_child(dossier_node, "maatregel")
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (5, 5)


async def test_progress_multiple_dossiers(db_session, make_child):
    """Progress is computed independently per dossier."""
    d1 = CorpusNode(id=uuid.uuid4(), title="D1", node_type="dossier", status="actief")
    d2 = CorpusNode(id=uuid.uuid4(), title="D2", node_type="dossier", status="actief")
    db_session.add_all([d1, d2])
    await db_session.flush()

    await make_child(d1, "probleem")
    await make_child(d1, "doel")
    await make_child(d2, "effect")

    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([d1.id, d2.id])
    assert result[d1.id] == (2, 5)
    assert result[d2.id] == (1, 5)


async def test_progress_duplicate_types_dont_double_count(
    db_session, dossier_node, make_child
):
    """Multiple nodes of the same type still count as one step."""
    await make_child(dossier_node, "probleem", title="Probleem 1")
    await make_child(dossier_node, "probleem", title="Probleem 2")
    repo = CorpusNodeRepository(db_session)
    result = await repo.get_beleidskompas_progress([dossier_node.id])
    assert result[dossier_node.id] == (1, 5)


# ---------------------------------------------------------------------------
# API: list nodes enrichment
# ---------------------------------------------------------------------------


async def test_list_nodes_includes_progress(client, db_session, onderdeel_van_type):
    """GET /api/nodes returns beleidskompas_progress for dossier nodes."""
    dossier = CorpusNode(
        id=uuid.uuid4(),
        title="API dossier",
        node_type="dossier",
        status="actief",
    )
    child = CorpusNode(
        id=uuid.uuid4(),
        title="API probleem",
        node_type="probleem",
        status="actief",
    )
    db_session.add_all([dossier, child])
    await db_session.flush()
    db_session.add(
        Edge(
            id=uuid.uuid4(),
            from_node_id=child.id,
            to_node_id=dossier.id,
            edge_type_id="onderdeel_van",
        )
    )
    await db_session.flush()

    resp = await client.get("/api/nodes", params={"node_type": "dossier"})
    assert resp.status_code == 200
    data = resp.json()
    matched = [n for n in data if n["id"] == str(dossier.id)]
    assert len(matched) == 1
    progress = matched[0]["beleidskompas_progress"]
    assert progress is not None
    assert progress["completed_steps"] == 1
    assert progress["total_steps"] == 5


async def test_list_nodes_non_dossier_no_progress(client, db_session):
    """Non-dossier nodes should not have beleidskompas_progress."""
    node = CorpusNode(
        id=uuid.uuid4(),
        title="API doel",
        node_type="doel",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    resp = await client.get("/api/nodes", params={"node_type": "doel"})
    assert resp.status_code == 200
    data = resp.json()
    matched = [n for n in data if n["id"] == str(node.id)]
    assert len(matched) == 1
    assert matched[0]["beleidskompas_progress"] is None
