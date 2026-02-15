"""Tests for bouwmeester.core.async_cache."""

import asyncio

import pytest

from bouwmeester.core.async_cache import AsyncTTLCache


class TestAsyncTTLCache:
    def test_empty_cache_returns_none(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=60)
        assert cache.get_if_fresh() is None

    def test_set_and_get(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=60)
        cache.set("hello")
        assert cache.get_if_fresh() == "hello"

    def test_stale_after_ttl(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=0)
        cache.set("hello")
        # TTL of 0 means immediately stale
        assert cache.get_if_fresh() is None

    def test_get_stale_returns_value_regardless_of_ttl(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=0)
        cache.set("hello")
        # get_if_fresh returns None (expired), but get_stale still returns value
        assert cache.get_if_fresh() is None
        assert cache.get_stale() == "hello"

    def test_get_stale_empty_cache(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=60)
        assert cache.get_stale() is None

    def test_set_resets_ttl(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=0.05)
        cache.set("first")
        # Immediately fresh
        assert cache.get_if_fresh() == "first"
        # Overwrite resets timer
        cache.set("second")
        assert cache.get_if_fresh() == "second"

    def test_lock_is_asyncio_lock(self):
        cache: AsyncTTLCache[str] = AsyncTTLCache(ttl=60)
        assert isinstance(cache.lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_access(self):
        cache: AsyncTTLCache[int] = AsyncTTLCache(ttl=60)
        results = []

        async def worker(value: int):
            async with cache.lock:
                results.append(value)
                await asyncio.sleep(0.01)

        await asyncio.gather(worker(1), worker(2))
        # Both complete; order depends on scheduling but both should be present
        assert sorted(results) == [1, 2]

    def test_set_overwrites_previous_value(self):
        cache: AsyncTTLCache[dict] = AsyncTTLCache(ttl=60)
        cache.set({"a": 1})
        cache.set({"b": 2})
        assert cache.get_if_fresh() == {"b": 2}
