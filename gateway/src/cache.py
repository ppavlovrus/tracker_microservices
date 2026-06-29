"""Redis cache helper for the Gateway (cache-aside pattern).

The cache is best-effort: any Redis failure is logged and swallowed so the
gateway keeps serving requests straight through the RabbitMQ RPC path. A dead
Redis must never take the gateway down with it.
"""

import json
import logging
from typing import Any, Optional

from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class Cache:
    """Thin async wrapper around Redis with JSON (de)serialization.

    Every operation degrades gracefully: on any Redis error reads return None
    (treated as a cache miss) and writes/deletes become no-ops.
    """

    def __init__(self, redis_url: str, enabled: bool = True):
        self._redis_url = redis_url
        self._enabled = enabled
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Open the connection and ping. On failure the cache stays disabled."""
        if not self._enabled:
            logger.info("Cache disabled via config")
            return

        # Short socket timeouts so a hung/unreachable Redis degrades to a cache
        # miss quickly instead of stalling the request on the RPC fast path.
        client = aioredis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            await client.ping()
        except RedisError as e:
            logger.warning(f"Redis unavailable, cache disabled: {e}")
            await client.aclose()
            return

        self._client = client
        logger.info(f"Cache connected: {self._redis_url}")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(self, key: str) -> Optional[Any]:
        """Return the cached value for ``key`` or None on miss/error."""
        if self._client is None:
            return None
        try:
            raw = await self._client.get(key)
        except RedisError as e:
            logger.warning(f"Cache GET failed for {key}: {e}")
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            logger.warning(f"Corrupt cache value for {key}, ignoring")
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        """Store ``value`` as JSON under ``key`` with a TTL in seconds."""
        if self._client is None:
            return
        try:
            await self._client.set(key, json.dumps(value), ex=ttl)
        except (RedisError, TypeError) as e:
            logger.warning(f"Cache SET failed for {key}: {e}")

    async def delete(self, *keys: str) -> None:
        """Delete one or more keys (used for point invalidation)."""
        if self._client is None or not keys:
            return
        try:
            await self._client.delete(*keys)
        except RedisError as e:
            logger.warning(f"Cache DELETE failed for {keys}: {e}")

    async def delete_pattern(self, pattern: str) -> None:
        """Delete every key matching ``pattern`` (e.g. ``tags:list:*``).

        Uses SCAN rather than KEYS so it never blocks the Redis event loop.
        """
        if self._client is None:
            return
        try:
            keys = [key async for key in self._client.scan_iter(match=pattern, count=100)]
            if keys:
                await self._client.delete(*keys)
        except RedisError as e:
            logger.warning(f"Cache DELETE pattern {pattern} failed: {e}")
