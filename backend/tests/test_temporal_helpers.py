"""Tests for bouwmeester.repositories.temporal helpers."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_status import CorpusNodeStatus
from bouwmeester.models.node_title import CorpusNodeTitle
from bouwmeester.repositories.temporal import (
    close_active_records,
    rotate_temporal_record,
)


@pytest.fixture
async def temporal_node(db_session: AsyncSession):
    """Create a corpus node with an active title and status record."""
    node_id = uuid.uuid4()
    node = CorpusNode(
        id=node_id,
        title="Temporal Test",
        node_type="dossier",
        description="",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    title = CorpusNodeTitle(
        node_id=node_id,
        title="Temporal Test",
        geldig_van=date(2024, 1, 1),
    )
    status = CorpusNodeStatus(
        node_id=node_id,
        status="actief",
        geldig_van=date(2024, 1, 1),
    )
    db_session.add_all([title, status])
    await db_session.flush()
    return node


class TestRotateTemporalRecord:
    async def test_closes_active_and_inserts_new(
        self, db_session: AsyncSession, temporal_node
    ):
        effective = date(2025, 6, 1)
        new_title = CorpusNodeTitle(
            node_id=temporal_node.id,
            title="Renamed",
            geldig_van=effective,
        )
        await rotate_temporal_record(
            db_session,
            CorpusNodeTitle,
            CorpusNodeTitle.node_id,
            temporal_node.id,
            effective,
            new_title,
        )
        await db_session.flush()

        result = await db_session.execute(
            select(CorpusNodeTitle)
            .where(CorpusNodeTitle.node_id == temporal_node.id)
            .order_by(CorpusNodeTitle.geldig_van)
        )
        records = result.scalars().all()

        assert len(records) == 2
        # Old record closed
        assert records[0].title == "Temporal Test"
        assert records[0].geldig_tot == effective
        # New record open
        assert records[1].title == "Renamed"
        assert records[1].geldig_van == effective
        assert records[1].geldig_tot is None

    async def test_close_only_when_new_record_is_none(
        self, db_session: AsyncSession, temporal_node
    ):
        effective = date(2025, 6, 1)
        await rotate_temporal_record(
            db_session,
            CorpusNodeTitle,
            CorpusNodeTitle.node_id,
            temporal_node.id,
            effective,
            None,
        )
        await db_session.flush()

        result = await db_session.execute(
            select(CorpusNodeTitle).where(CorpusNodeTitle.node_id == temporal_node.id)
        )
        records = result.scalars().all()

        assert len(records) == 1
        assert records[0].geldig_tot == effective

    async def test_no_active_record_still_inserts(
        self, db_session: AsyncSession, temporal_node
    ):
        """When there is no active record, the new record is still inserted."""
        # Close existing record first
        result = await db_session.execute(
            select(CorpusNodeTitle).where(CorpusNodeTitle.node_id == temporal_node.id)
        )
        existing = result.scalar_one()
        existing.geldig_tot = date(2025, 1, 1)
        await db_session.flush()

        effective = date(2025, 6, 1)
        new_title = CorpusNodeTitle(
            node_id=temporal_node.id,
            title="Fresh Start",
            geldig_van=effective,
        )
        await rotate_temporal_record(
            db_session,
            CorpusNodeTitle,
            CorpusNodeTitle.node_id,
            temporal_node.id,
            effective,
            new_title,
        )
        await db_session.flush()

        result = await db_session.execute(
            select(CorpusNodeTitle).where(
                CorpusNodeTitle.node_id == temporal_node.id,
                CorpusNodeTitle.geldig_tot.is_(None),
            )
        )
        active = result.scalar_one()
        assert active.title == "Fresh Start"


class TestCloseActiveRecords:
    async def test_closes_all_model_types(
        self, db_session: AsyncSession, temporal_node
    ):
        end = date(2025, 12, 31)
        await close_active_records(
            db_session,
            [
                (CorpusNodeTitle, CorpusNodeTitle.node_id),
                (CorpusNodeStatus, CorpusNodeStatus.node_id),
            ],
            temporal_node.id,
            end,
        )
        await db_session.flush()

        for model_cls in (CorpusNodeTitle, CorpusNodeStatus):
            result = await db_session.execute(
                select(model_cls).where(
                    model_cls.node_id == temporal_node.id,
                    model_cls.geldig_tot.is_(None),
                )
            )
            assert result.scalar_one_or_none() is None, (
                f"{model_cls.__name__} still has an active record"
            )

    async def test_does_not_affect_other_nodes(
        self, db_session: AsyncSession, temporal_node
    ):
        """Closing records for one node doesn't affect another."""
        other_id = uuid.uuid4()
        other_node = CorpusNode(
            id=other_id,
            title="Other",
            node_type="doel",
            description="",
            status="actief",
        )
        db_session.add(other_node)
        await db_session.flush()

        other_title = CorpusNodeTitle(
            node_id=other_id,
            title="Other",
            geldig_van=date(2024, 1, 1),
        )
        db_session.add(other_title)
        await db_session.flush()

        await close_active_records(
            db_session,
            [(CorpusNodeTitle, CorpusNodeTitle.node_id)],
            temporal_node.id,
            date(2025, 12, 31),
        )
        await db_session.flush()

        result = await db_session.execute(
            select(CorpusNodeTitle).where(
                CorpusNodeTitle.node_id == other_id,
                CorpusNodeTitle.geldig_tot.is_(None),
            )
        )
        assert result.scalar_one_or_none() is not None
