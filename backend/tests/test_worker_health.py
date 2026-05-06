"""Tests for worker-health upsert and the /api/admin/workers classifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from bouwmeester.api.routes.admin import _classify_health
from bouwmeester.models.worker_heartbeat import WorkerHeartbeat
from bouwmeester.services.worker_health import _upsert


class TestClassifyHealth:
    """The classifier maps (status, age, cadence) to a UI bucket."""

    def test_recent_ok_is_healthy(self):
        assert (
            _classify_health("ok", seconds_since=10, expected_cadence=60) == "healthy"
        )

    def test_disabled_short_circuits(self):
        # Even with a stale tick, "disabled" stays disabled.
        assert (
            _classify_health("disabled", seconds_since=99999, expected_cadence=60)
            == "disabled"
        )

    def test_slightly_late_is_stale(self):
        assert _classify_health("ok", seconds_since=120, expected_cadence=60) == "stale"

    def test_very_late_is_down(self):
        assert _classify_health("ok", seconds_since=300, expected_cadence=60) == "down"

    def test_error_status_marks_stale_even_when_recent(self):
        # We tick on error, so the row is fresh; surface it as stale not
        # healthy so operators see something is off.
        assert (
            _classify_health("error", seconds_since=5, expected_cadence=60) == "stale"
        )

    def test_reconnecting_marks_stale(self):
        assert (
            _classify_health("reconnecting", seconds_since=5, expected_cadence=60)
            == "stale"
        )


@pytest.mark.asyncio
class TestUpsert:
    """`_upsert` writes a row on first call and updates it on subsequent calls."""

    async def test_first_tick_creates_row(self, db_session):
        await _upsert(db_session, "test_loop", status="ok", detail="first")
        row = (
            await db_session.execute(
                select(WorkerHeartbeat).where(WorkerHeartbeat.loop_name == "test_loop")
            )
        ).scalar_one()
        assert row.status == "ok"
        assert row.detail == "first"
        assert row.started_at is not None

    async def test_second_tick_updates_in_place(self, db_session):
        await _upsert(db_session, "test_loop", status="starting", detail=None)
        first = (
            await db_session.execute(
                select(WorkerHeartbeat).where(WorkerHeartbeat.loop_name == "test_loop")
            )
        ).scalar_one()
        first_id = first.id
        first_started = first.started_at

        await _upsert(db_session, "test_loop", status="ok", detail="cycle complete")
        # Drop identity-map cache — the upsert ran via raw SQL so the
        # ORM doesn't know the row's status field changed.
        db_session.expire_all()
        second = (
            await db_session.execute(
                select(WorkerHeartbeat).where(WorkerHeartbeat.loop_name == "test_loop")
            )
        ).scalar_one()
        # Same row (id stable, started_at preserved); status/detail/last_tick updated.
        assert second.id == first_id
        assert second.started_at == first_started
        assert second.status == "ok"
        assert second.detail == "cycle complete"

    async def test_tick_advances_last_tick_at(self, db_session):
        await _upsert(db_session, "test_loop", status="ok", detail=None)
        first = (
            await db_session.execute(
                select(WorkerHeartbeat).where(WorkerHeartbeat.loop_name == "test_loop")
            )
        ).scalar_one()
        first_tick = first.last_tick_at

        await _upsert(db_session, "test_loop", status="ok", detail="next")
        db_session.expire_all()
        second = (
            await db_session.execute(
                select(WorkerHeartbeat).where(WorkerHeartbeat.loop_name == "test_loop")
            )
        ).scalar_one()
        # last_tick should not move backwards; on a fast machine two ticks
        # may share a microsecond, so we just assert non-decreasing.
        a = first_tick if first_tick.tzinfo else first_tick.replace(tzinfo=UTC)
        b = (
            second.last_tick_at
            if second.last_tick_at.tzinfo
            else second.last_tick_at.replace(tzinfo=UTC)
        )
        assert b >= a
        # And the gap to "now" is small (we just wrote it).
        assert (datetime.now(UTC) - b) < timedelta(seconds=10)
