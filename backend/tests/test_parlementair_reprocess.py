"""Tests for ParlementairImportService.reprocess_imported_items and related methods."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.politieke_input import PolitiekeInput
from bouwmeester.models.tag import NodeTag, Tag
from bouwmeester.models.task import Task
from bouwmeester.services.llm.base import TagExtractionResult
from bouwmeester.services.parlementair_import_service import ParlementairImportService

# Tests use item_type="motie" to avoid collisions with real toezegging
# data that may exist in the test database.
TEST_TYPE = "motie"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_item(db_session, *, with_node=True, with_edges=0, status="imported"):
    """Create an imported parlementair item with optional corpus node and edges."""
    node = None
    if with_node:
        node = CorpusNode(
            id=uuid.uuid4(),
            title="Test node",
            node_type="politieke_input",
            description="Zaak: test",
            status="actief",
        )
        db_session.add(node)
        await db_session.flush()

        pi = PolitiekeInput(
            id=node.id,
            type="motie",
            referentie="36200-VII-42",
            status="open",
        )
        db_session.add(pi)
        await db_session.flush()

    item = ParlementairItem(
        id=uuid.uuid4(),
        type=TEST_TYPE,
        zaak_id=f"zaak-{uuid.uuid4().hex[:8]}",
        zaak_nummer="36200-VII-42",
        titel="Test motie",
        onderwerp="De Kamer verzoekt de minister iets te doen",
        bron="tweede_kamer",
        datum=date(2025, 1, 15),
        status=status,
        corpus_node_id=node.id if node else None,
    )
    db_session.add(item)
    await db_session.flush()

    if with_edges > 0 and node:
        target = CorpusNode(
            id=uuid.uuid4(),
            title="Beleidsdossier",
            node_type="dossier",
            status="actief",
        )
        db_session.add(target)
        await db_session.flush()
        for _ in range(with_edges):
            se = SuggestedEdge(
                id=uuid.uuid4(),
                parlementair_item_id=item.id,
                target_node_id=target.id,
                edge_type_id="adresseert",
                confidence=0.8,
                reason="test",
                status="pending",
            )
            db_session.add(se)
        await db_session.flush()

    return item, node


def _mock_llm(matched_tags=None, samenvatting="Samenvatting"):
    """Create a mock LLM service returning the given tags."""
    mock = AsyncMock()
    mock.extract_tags.return_value = TagExtractionResult(
        matched_tags=matched_tags or [],
        suggested_new_tags=[],
        samenvatting=samenvatting,
    )
    return mock


# ---------------------------------------------------------------------------
# reprocess_imported_items — basic scenarios
# ---------------------------------------------------------------------------


async def test_reprocess_no_items_to_process(db_session):
    """Reprocess returns zeros when no items need processing."""
    service = ParlementairImportService(db_session)
    result = await service.reprocess_imported_items(item_type=TEST_TYPE)
    assert result == {"total": 0, "matched": 0, "out_of_scope": 0, "skipped": 0}


async def test_reprocess_skips_items_with_existing_edges(db_session):
    """Items that already have suggested edges are not reprocessed."""
    await _make_item(db_session, with_edges=1)
    service = ParlementairImportService(db_session)
    result = await service.reprocess_imported_items(item_type=TEST_TYPE)
    assert result["total"] == 0


async def test_reprocess_picks_up_pending_items(db_session):
    """Pending items (from earlier LLM failures) are also reprocessed."""
    item, _ = await _make_item(db_session, status="pending", with_node=False)

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[])),
    ):
        result = await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert result["total"] == 1
    assert item.status == "out_of_scope"


async def test_reprocess_no_llm_provider(db_session):
    """Reprocess returns error when no LLM provider is configured."""
    await _make_item(db_session)
    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=None),
    ):
        result = await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert result["total"] == 1
    assert result["error"] == "no_llm"


# ---------------------------------------------------------------------------
# reprocess — out_of_scope path (no matches → detach node)
# ---------------------------------------------------------------------------


async def test_reprocess_no_matches_moves_to_out_of_scope(db_session):
    """Items without matches after LLM are moved to out_of_scope."""
    item, node = await _make_item(db_session)
    node_id = node.id

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[])),
    ):
        result = await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert result["total"] == 1
    assert result["out_of_scope"] == 1
    assert result["matched"] == 0
    assert item.status == "out_of_scope"
    assert item.corpus_node_id is None

    # Corpus node should be deleted
    deleted_node = await db_session.get(CorpusNode, node_id)
    assert deleted_node is None


async def test_reprocess_no_matches_cascade_deletes_tasks(db_session):
    """Tasks linked to the corpus node are cascade-deleted when node is removed."""
    item, node = await _make_item(db_session)

    task = Task(
        id=uuid.uuid4(),
        node_id=node.id,
        title="Beoordeel motie",
        status="open",
        priority="normaal",
        parlementair_item_id=item.id,
    )
    db_session.add(task)
    await db_session.flush()
    task_id = task.id

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[])),
    ):
        await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert item.status == "out_of_scope"
    assert item.corpus_node_id is None
    # Task is cascade-deleted with the corpus node (ondelete=CASCADE on Task.node_id)
    assert await db_session.get(Task, task_id) is None


async def test_reprocess_no_matches_deletes_politieke_input(db_session):
    """PolitiekeInput record is cascade-deleted with the corpus node."""
    item, node = await _make_item(db_session)
    node_id = node.id

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[])),
    ):
        await service.reprocess_imported_items(item_type=TEST_TYPE)

    pi = await db_session.get(PolitiekeInput, node_id)
    assert pi is None


# ---------------------------------------------------------------------------
# reprocess — match path (LLM finds tags → suggested edges created)
# ---------------------------------------------------------------------------


async def test_reprocess_with_matches_creates_edges(db_session):
    """Items with matching tags get suggested edges created."""
    # Create a tag and a dossier node that has that tag
    tag = Tag(id=uuid.uuid4(), name=f"test_tag_{uuid.uuid4().hex[:6]}")
    db_session.add(tag)
    await db_session.flush()

    target_node = CorpusNode(
        id=uuid.uuid4(),
        title="Woningbouwdossier",
        node_type="dossier",
        status="actief",
    )
    db_session.add(target_node)
    await db_session.flush()

    node_tag = NodeTag(tag_id=tag.id, node_id=target_node.id)
    db_session.add(node_tag)
    await db_session.flush()

    item, _ = await _make_item(db_session)

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[tag.name])),
    ):
        result = await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert result["matched"] == 1
    assert result["out_of_scope"] == 0

    # Verify suggested edge was created
    edges_result = await db_session.execute(
        select(SuggestedEdge).where(SuggestedEdge.parlementair_item_id == item.id)
    )
    edges = edges_result.scalars().all()
    assert len(edges) >= 1
    assert edges[0].target_node_id == target_node.id
    assert edges[0].status == "pending"


async def test_reprocess_with_matches_tags_corpus_node(db_session):
    """Matching items get their corpus node tagged."""
    tag = Tag(id=uuid.uuid4(), name=f"test_tag_{uuid.uuid4().hex[:6]}")
    db_session.add(tag)
    await db_session.flush()

    target_node = CorpusNode(
        id=uuid.uuid4(),
        title="Digitaliseringsdossier",
        node_type="dossier",
        status="actief",
    )
    db_session.add(target_node)
    await db_session.flush()

    node_tag = NodeTag(tag_id=tag.id, node_id=target_node.id)
    db_session.add(node_tag)
    await db_session.flush()

    item, node = await _make_item(db_session)

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[tag.name])),
    ):
        await service.reprocess_imported_items(item_type=TEST_TYPE)

    # Verify tag was added to the item's corpus node
    tag_result = await db_session.execute(
        select(NodeTag).where(NodeTag.node_id == node.id)
    )
    tags = tag_result.scalars().all()
    assert len(tags) == 1
    assert tags[0].tag_id == tag.id


async def test_reprocess_updates_llm_fields(db_session):
    """Reprocess stores matched_tags and samenvatting on the item."""
    item, _ = await _make_item(db_session)
    assert item.matched_tags is None
    assert item.llm_samenvatting is None

    service = ParlementairImportService(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(
            return_value=_mock_llm(
                matched_tags=["test_tag"],
                samenvatting="LLM samenvatting",
            )
        ),
    ):
        await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert item.matched_tags == ["test_tag"]
    assert item.llm_samenvatting == "LLM samenvatting"


# ---------------------------------------------------------------------------
# reprocess — LLM failure (skipped count)
# ---------------------------------------------------------------------------


async def test_reprocess_llm_failure_skips_item(db_session):
    """Items where LLM extraction fails are skipped and counted."""
    await _make_item(db_session)

    service = ParlementairImportService(db_session)

    failing_llm = AsyncMock()
    failing_llm.extract_tags.side_effect = Exception("LLM timeout")

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=failing_llm),
    ):
        result = await service.reprocess_imported_items(item_type=TEST_TYPE)

    assert result["total"] == 1
    assert result["skipped"] == 1
    assert result["matched"] == 0
    assert result["out_of_scope"] == 0


# ---------------------------------------------------------------------------
# _detach_corpus_node — unit tests
# ---------------------------------------------------------------------------


async def test_detach_corpus_node_deletes_node(db_session):
    """_detach_corpus_node deletes the corpus node and clears the FK."""
    item, node = await _make_item(db_session)
    node_id = node.id

    service = ParlementairImportService(db_session)
    await service._detach_corpus_node(item)

    assert item.corpus_node_id is None
    assert await db_session.get(CorpusNode, node_id) is None


async def test_detach_corpus_node_cascade_deletes_tasks(db_session):
    """_detach_corpus_node cascade-deletes tasks linked to the corpus node."""
    item, node = await _make_item(db_session)

    open_task = Task(
        id=uuid.uuid4(),
        node_id=node.id,
        title="Open task",
        status="open",
        priority="normaal",
        parlementair_item_id=item.id,
    )
    db_session.add(open_task)
    await db_session.flush()

    service = ParlementairImportService(db_session)
    await service._detach_corpus_node(item)

    assert item.corpus_node_id is None
    assert await db_session.get(CorpusNode, node.id) is None
    # Task is cascade-deleted with the corpus node
    assert await db_session.get(Task, open_task.id) is None


async def test_detach_corpus_node_no_node_is_noop(db_session):
    """_detach_corpus_node is safe to call when corpus_node_id is None."""
    item, _ = await _make_item(db_session, with_node=False)
    assert item.corpus_node_id is None

    service = ParlementairImportService(db_session)
    await service._detach_corpus_node(item)  # should not raise

    assert item.corpus_node_id is None


# ---------------------------------------------------------------------------
# _process_item — LLM failure creates pending item (not orphan node)
# ---------------------------------------------------------------------------


async def test_process_item_llm_failure_creates_pending(db_session):
    """When LLM fails, _process_item saves item as pending (no node)."""
    from bouwmeester.services.import_strategies.base import FetchedItem
    from bouwmeester.services.import_strategies.registry import get_strategy

    fetched = FetchedItem(
        zaak_id=f"tz-{uuid.uuid4().hex[:8]}",
        zaak_nummer="TZ202502-999",
        titel="Test toezegging",
        onderwerp="Minister zegt iets toe",
        bron="tweede_kamer",
        datum=date(2025, 2, 1),
        ministerie="Binnenlandse Zaken en Koninkrijksrelaties",
    )

    service = ParlementairImportService(db_session)
    strategy = get_strategy("toezegging")

    failing_llm = AsyncMock()
    failing_llm.extract_tags.side_effect = Exception("LLM down")

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=failing_llm),
    ):
        result = await service._process_item(fetched, strategy)

    assert result is False

    # Verify item was saved as pending
    created = await service.import_repo.get_by_zaak_id(fetched.zaak_id)
    assert created is not None
    assert created.status == "pending"
    assert created.corpus_node_id is None


async def test_process_item_no_llm_provider_creates_pending(db_session):
    """When no LLM provider is configured, item is saved as pending."""
    from bouwmeester.services.import_strategies.base import FetchedItem
    from bouwmeester.services.import_strategies.registry import get_strategy

    fetched = FetchedItem(
        zaak_id=f"tz-{uuid.uuid4().hex[:8]}",
        zaak_nummer="TZ202502-998",
        titel="Test toezegging 2",
        onderwerp="Nog een toezegging",
        bron="tweede_kamer",
        datum=date(2025, 2, 1),
        ministerie="Binnenlandse Zaken en Koninkrijksrelaties",
    )

    service = ParlementairImportService(db_session)
    strategy = get_strategy("toezegging")

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=None),
    ):
        result = await service._process_item(fetched, strategy)

    assert result is False

    created = await service.import_repo.get_by_zaak_id(fetched.zaak_id)
    assert created is not None
    assert created.status == "pending"
    assert created.corpus_node_id is None


# ---------------------------------------------------------------------------
# Reprocess API endpoint
# ---------------------------------------------------------------------------


async def test_reprocess_endpoint_returns_result(client, db_session):
    """POST /api/parlementair/imports/reprocess returns reprocess results."""
    await _make_item(db_session)

    with patch(
        "bouwmeester.services.parlementair_import_service.get_llm_service",
        new=AsyncMock(return_value=_mock_llm(matched_tags=[])),
    ):
        resp = await client.post(
            "/api/parlementair/imports/reprocess",
            params={"item_type": TEST_TYPE},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "matched" in data
    assert "out_of_scope" in data
    assert "skipped" in data
