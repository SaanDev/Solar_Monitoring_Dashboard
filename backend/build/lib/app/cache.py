"""Tiny Redis JSON cache.

Used to wrap latest/range API responses. Every operation degrades gracefully:
if Redis is unreachable, reads miss and writes no-op, so the app keeps working
(serving from the DB / live sources) without Redis in dev or test.

With ``REDIS_URL`` empty or ``memory://`` (the desktop app, which runs as a
single process with no Redis server) an in-process TTL store stands in instead.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | MemoryCache | None = None


class MemoryCache:
    """In-process stand-in for the three Redis calls this module makes.

    Enough for one backend process: entries expire lazily on read, and a sweep
    on write keeps keys that are never read again from piling up.
    """

    _SWEEP_EVERY = 256

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._writes = 0

    async def get(self, key: str) -> str | None:
        hit = self._store.get(key)
        if hit is None:
            return None
        value, expires_at = hit
        if expires_at is not None and expires_at <= time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        now = time.monotonic()
        self._store[key] = (value, now + ex if ex else None)
        self._writes += 1
        if self._writes % self._SWEEP_EVERY == 0:
            expired = [k for k, (_, exp) in self._store.items() if exp is not None and exp <= now]
            for k in expired:
                del self._store[k]

    async def aclose(self) -> None:
        self._store.clear()


def _uses_memory_cache() -> bool:
    url = settings.redis_url.strip()
    return not url or url.startswith("memory://")


def get_client() -> aioredis.Redis | MemoryCache:
    """Lazily create the shared cache client (Redis, or in-process)."""
    global _client
    if _client is None:
        if _uses_memory_cache():
            _client = MemoryCache()
        else:
            # Short timeouts so a missing Redis degrades quickly instead of hanging.
            _client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
    return _client


async def cache_get_json(key: str) -> Any | None:
    """Return the decoded JSON value for ``key``, or ``None`` on miss/error."""
    try:
        raw = await get_client().get(key)
    except Exception as exc:  # connection refused, timeout, etc.
        logger.debug("cache get failed for %s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def cache_set_json(key: str, value: Any, ttl: int) -> None:
    """Store ``value`` as JSON under ``key`` with a TTL (seconds). Best-effort."""
    try:
        await get_client().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.debug("cache set failed for %s: %s", key, exc)


async def close_cache() -> None:
    """Close the shared client (call on app shutdown)."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None
