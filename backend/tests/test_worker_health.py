"""Tests for worker-health upsert and the /api/admin/workers classifier."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from bouwmeester.api.routes.admin import (
    _ONE_SHOT_LOOPS,
    _classify_health,
    _expected_loops,
    _worker_expected_cadence_sec,
)
from bouwmeester.core.config import get_settings
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

    def test_error_beats_age(self):
        # An old *and* errored row is more useful as "stale" (we know why)
        # than as "down" (we don't).
        assert (
            _classify_health("error", seconds_since=99999, expected_cadence=60)
            == "stale"
        )


class TestOneShotClassification:
    """One-shot entries tick once by design; age must not condemn them.

    `worker_singleton` ticks when the instance wins the lock and then stays
    silent forever. Age-based classification called it "down" after five
    minutes, which is what made the admin page show a permanent red row.
    """

    def test_ancient_one_shot_stays_healthy(self):
        assert (
            _classify_health(
                "ok", seconds_since=15 * 86400, expected_cadence=300, one_shot=True
            )
            == "healthy"
        )

    def test_one_shot_waiting_is_stale(self):
        # Status still carries signal: waiting for the lock is not healthy.
        assert (
            _classify_health(
                "waiting", seconds_since=10, expected_cadence=300, one_shot=True
            )
            == "stale"
        )

    def test_one_shot_error_is_stale(self):
        assert (
            _classify_health(
                "error", seconds_since=10, expected_cadence=300, one_shot=True
            )
            == "stale"
        )

    def test_worker_singleton_is_registered_one_shot(self):
        assert "worker_singleton" in _ONE_SHOT_LOOPS


class TestExpectedCadence:
    """The cadence map must cover every loop the worker actually starts."""

    def test_covers_every_worker_loop(self):
        # Guard against the drift that caused this bug: a loop added to
        # worker.py but not here falls back to a 300s cadence and shows up
        # as "down" within minutes.
        import bouwmeester.worker as worker_module

        source = Path(worker_module.__file__).read_text()
        started = set(re.findall(r'health_tick\(\s*"([a-z_]+)"', source))
        assert started, "no health_tick calls found — did worker.py move?"
        assert started <= set(_expected_loops()), (
            f"loops without a cadence entry: {started - set(_expected_loops())}"
        )

    def test_cadence_follows_settings(self):
        # Hardcoded numbers drifted from the settings the loops sleep on
        # (900 here vs a 3600 default), turning a healthy loop amber.
        settings = get_settings()
        cadences = _worker_expected_cadence_sec()
        assert cadences["parlementair"] == float(settings.TK_POLL_INTERVAL_SECONDS)
        assert cadences["fcc_sync"] == float(settings.FCC_POLL_INTERVAL_SECONDS)
        assert cadences["overheidsorganisaties_daily"] == float(
            settings.OVERHEIDSORG_DAILY_INTERVAL_SECONDS
        )
        assert cadences["overheidsorganisaties_weekly"] == float(
            settings.OVERHEIDSORG_WEEKLY_INTERVAL_SECONDS
        )

    def test_daily_loop_is_not_down_after_18_hours(self):
        # The exact production symptom: a daily loop 18h into its 24h cycle
        # was rendered "Niet actief".
        cadence = _worker_expected_cadence_sec()["overheidsorganisaties_daily"]
        assert _classify_health(
            "ok", seconds_since=18 * 3600, expected_cadence=cadence
        ) == ("healthy")


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
