"""Redis-backed session store for the Gateway.

Sessions are opaque tokens mapped to a small JSON record (user id / username /
email) under ``sess:<token>`` with a TTL. Redis expiry doubles as session
expiry, so there is no cleanup job to run.

Unlike the cache and the rate limiter, the session store **fails closed**: if
Redis is unreachable, session lookups return ``None`` (the request is treated
as unauthenticated) instead of being waved through. A login gate that fails
open is not a gate at all.
"""

import json
import logging
import secrets
from typing import Any, Dict, Optional

from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class SessionStore:
    """Opaque session tokens stored in Redis with a TTL."""

    def __init__(self, redis_url: str, ttl: int, enabled: bool = True):
        self._redis_url = redis_url
        self._ttl = ttl
        self._enabled = enabled
        self._client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Open the connection and ping. On failure the store stays down."""
        if not self._enabled:
            logger.info("Session store disabled via config")
            return

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
            logger.warning(f"Redis unavailable, session store down: {e}")
            await client.aclose()
            return

        self._client = client
        logger.info(f"Session store connected: {self._redis_url}")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _key(token: str) -> str:
        return f"sess:{token}"

    async def create(self, user: Dict[str, Any]) -> Optional[str]:
        """Create a session for ``user`` and return its token.

        Returns ``None`` if the session could not be persisted (Redis down) so
        the caller can refuse the login instead of handing out a token that
        was never stored.
        """
        if self._client is None:
            return None
        token = secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "user_id": user["id"],
                "username": user["username"],
                "email": user.get("email"),
            }
        )
        try:
            await self._client.set(self._key(token), payload, ex=self._ttl)
        except RedisError as e:
            logger.warning(f"Session create failed: {e}")
            return None
        return token

    async def get(self, token: str) -> Optional[Dict[str, Any]]:
        """Return the session record for ``token`` or None (fail closed)."""
        if self._client is None or not token:
            return None
        try:
            raw = await self._client.get(self._key(token))
        except RedisError as e:
            logger.warning(f"Session lookup failed: {e}")
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("Corrupt session value, ignoring")
            return None

    async def delete(self, token: str) -> None:
        """Delete a session (logout). Best-effort."""
        if self._client is None or not token:
            return
        try:
            await self._client.delete(self._key(token))
        except RedisError as e:
            logger.warning(f"Session delete failed: {e}")
