"""Generic async TTL cache with double-checked locking."""

from __future__ import annotations

import asyncio
import time


class AsyncTTLCache[T]:
    """Thread-safe async cache that refreshes values after a TTL expires.

    Uses double-checked locking to avoid redundant fetches when multiple
    coroutines race to refresh a stale entry.

    Usage::

        cache = AsyncTTLCache[dict](ttl=3600)
        value = cache.get()           # Returns cached value or None
        cache.set(new_value)          # Update the cached value
    """

    def __init__(self, ttl: float) -> None:
        self._value: T | None = None
        self._fetched_at: float = 0
        self._lock = asyncio.Lock()
        self._ttl = ttl

    def get_if_fresh(self) -> T | None:
        """Return the cached value if still within TTL, else ``None``."""
        now = time.monotonic()
        if self._value is not None and (now - self._fetched_at) < self._ttl:
            return self._value
        return None

    def set(self, value: T) -> None:
        """Update the cached value and reset the TTL timer."""
        self._value = value
        self._fetched_at = time.monotonic()

    def get_stale(self) -> T | None:
        """Return the cached value regardless of TTL (may be ``None``)."""
        return self._value

    @property
    def lock(self) -> asyncio.Lock:
        """The internal lock, for use in double-checked locking patterns."""
        return self._lock
