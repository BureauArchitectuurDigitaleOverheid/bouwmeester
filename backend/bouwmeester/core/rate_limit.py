"""In-memory sliding-window rate limiter.

Provides a reusable rate limiter backed by an :class:`OrderedDict` with LRU
eviction.  Each instance maintains its own state so different endpoints can
use different limits.

NOTE: State is per-process — with multiple workers each has its own store,
so the effective limit is ``N × max_requests`` per window.  Acceptable for
moderate traffic; switch to Redis if stricter global limits are needed.
"""

from __future__ import annotations

import time
from collections import OrderedDict

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(
        self,
        *,
        window: int = 60,
        max_requests: int = 20,
        max_keys: int = 10_000,
    ) -> None:
        self.window = window
        self.max_requests = max_requests
        self.max_keys = max_keys
        self._store: OrderedDict[str, list[float]] = OrderedDict()

    @staticmethod
    def get_client_ip(request: Request) -> str:
        """Return the client IP from the direct TCP connection.

        X-Forwarded-For is intentionally NOT used because it is trivially
        spoofable by any client.  The direct ``request.client.host`` is set
        by the ASGI server from the TCP socket and cannot be forged.
        """
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        """Raise 429 if the client IP has exceeded the rate limit."""
        client_ip = self.get_client_ip(request)
        now = time.monotonic()
        window_start = now - self.window

        if client_ip not in self._store:
            self._store[client_ip] = []

        timestamps = self._store[client_ip]
        # In-place modification avoids race conditions between async
        # coroutines that could overwrite each other's appended timestamps.
        timestamps[:] = [t for t in timestamps if t > window_start]

        if len(timestamps) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, try again later",
            )

        timestamps.append(now)
        self._store.move_to_end(client_ip)

        while len(self._store) > self.max_keys:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """Clear all tracked state (useful for testing)."""
        self._store.clear()
