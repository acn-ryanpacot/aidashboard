"""A tiny async time-to-live cache for slow external lookups."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Generic, TypeVar

V = TypeVar("V")


class TtlCache(Generic[V]):
    """Caches the result of an async loader per key for ``ttl_s`` seconds.

    Concurrent requests for the same key share one in-flight load, so ten
    widgets asking for the weather at once cause a single HTTP request.

    Args:
        ttl_s: How long a value stays fresh.
        clock: Monotonic clock (injectable for tests).
    """

    def __init__(self, ttl_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._values: dict[Hashable, tuple[float, V]] = {}
        self._locks: dict[Hashable, asyncio.Lock] = {}

    async def get(self, key: Hashable, load: Callable[[], Awaitable[V]]) -> V:
        """Return the cached value for ``key``, loading it if stale or missing."""
        fresh = self._fresh(key)
        if fresh is not None:
            return fresh[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            fresh = self._fresh(key)
            if fresh is not None:
                return fresh[1]
            value = await load()
            self._values[key] = (self._clock(), value)
            return value

    def clear(self) -> None:
        """Forget everything (e.g. after the feed list changes)."""
        self._values.clear()

    def _fresh(self, key: Hashable) -> tuple[float, V] | None:
        entry = self._values.get(key)
        if entry is not None and self._clock() - entry[0] < self._ttl_s:
            return entry
        return None
