"""Tests voor de worker-singleton-lock-wait in bouwmeester.worker.main().

Bij een overlappende deploy mag een tweede worker-instantie niet ook de
achtergrond-loops starten; hij moet wachten tot de eerste stopt. Zie
``bouwmeester.core.worker_lock.WorkerLock`` voor de onderliggende
Postgres-advisory-lock."""

from unittest.mock import AsyncMock, patch

from bouwmeester import worker as worker_module


async def test_acquire_singleton_lock_or_wait_returns_immediately_when_free():
    lock = AsyncMock()
    lock.acquire = AsyncMock(return_value=True)

    with patch.object(worker_module, "health_tick", new=AsyncMock()) as health_tick:
        await worker_module._acquire_singleton_lock_or_wait(lock)

    lock.acquire.assert_awaited_once()
    health_tick.assert_awaited_once_with(
        "worker_singleton", status="ok", detail="lock verkregen"
    )


async def test_acquire_singleton_lock_or_wait_retries_until_free():
    """Als de lock al bezet is, moet de functie blijven pollen (zonder
    zelf door te gaan) tot een latere poging wél lukt."""
    lock = AsyncMock()
    lock.acquire = AsyncMock(side_effect=[False, False, True])

    with (
        patch.object(worker_module, "health_tick", new=AsyncMock()) as health_tick,
        patch.object(worker_module.asyncio, "sleep", new=AsyncMock()) as sleep,
    ):
        await worker_module._acquire_singleton_lock_or_wait(lock)

    assert lock.acquire.await_count == 3
    assert sleep.await_count == 2

    # Eerste tick meldt "waiting", laatste meldt "ok" — geen tussentijdse
    # duplicaten (de waiting-tick wordt maar één keer gelogd/geticked).
    statuses = [call.kwargs["status"] for call in health_tick.await_args_list]
    assert statuses == ["waiting", "ok"]
