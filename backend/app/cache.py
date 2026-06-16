"""Tiny Redis JSON cache.

Used to wrap latest/range API responses. Every operation degrades gracefully:
if Redis is unreachable, reads miss and writes no-op, so the app keeps working
(serving from the DB / live sources) without Redis in dev or test.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    """Lazily create a shared Redis client."""
    global _client
    if _client is None:
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
