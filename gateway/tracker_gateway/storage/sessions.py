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
from typing import Any

from redis import asyncio as aioredis
from redis.exceptions import RedisError

from ..core.config import AUTH_ENABLED, OAUTH_STATE_TTL, REDIS_URL, SESSION_TTL, YANDEX_OAUTH_ENABLED

logger = logging.getLogger(__name__)


class SessionStore:
    """Opaque session tokens stored in Redis with a TTL."""

    def __init__(self, redis_url: str, ttl: int, enabled: bool = True):
        self._redis_url = redis_url
        self._ttl = ttl
        self._enabled = enabled
        self._client: aioredis.Redis | None = None

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

    async def create(self, user: dict[str, Any]) -> str | None:
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

    async def get(self, token: str) -> dict[str, Any] | None:
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


class OAuthStateStore:
    """One-time CSRF ``state`` tokens for the OAuth flow, stored in Redis.

    Like the session store, this fails closed: if Redis is down, states cannot
    be issued or consumed, so the OAuth flow refuses to run rather than run
    without CSRF protection.
    """

    def __init__(self, redis_url: str, ttl: int):
        self._redis_url = redis_url
        self._ttl = ttl
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Open the connection and ping. On failure the store stays down."""
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
            logger.warning(f"Redis unavailable, OAuth state store down: {e}")
            await client.aclose()
            return

        self._client = client
        logger.info("OAuth state store connected")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _key(state: str) -> str:
        return f"oauth_state:{state}"

    async def issue(self) -> str | None:
        """Create and persist a fresh state token, or None if Redis is down."""
        if self._client is None:
            return None
        state = secrets.token_urlsafe(32)
        try:
            await self._client.set(self._key(state), "1", ex=self._ttl)
        except RedisError as e:
            logger.warning(f"OAuth state issue failed: {e}")
            return None
        return state

    async def consume(self, state: str) -> bool:
        """Atomically use up a state token. True only for a known, unused one."""
        if self._client is None or not state:
            return False
        try:
            deleted = await self._client.delete(self._key(state))
        except RedisError as e:
            logger.warning(f"OAuth state consume failed: {e}")
            return False
        return deleted == 1


# ── Lifecycle ────────────────────────────────────────────────
# Both stores are owned here rather than by the lifespan: the "is this
# configured at all?" question belongs to the module that knows what the
# answer means, which keeps the startup sequence free of feature flags.

session_store: SessionStore | None = None
oauth_state_store: OAuthStateStore | None = None


async def init_sessions() -> SessionStore:
    """Open the session store. Fails closed: a dead Redis blocks writes."""
    global session_store
    session_store = SessionStore(redis_url=REDIS_URL, ttl=SESSION_TTL, enabled=AUTH_ENABLED)
    await session_store.connect()
    return session_store


async def close_sessions() -> None:
    global session_store
    if session_store is not None:
        await session_store.close()
        session_store = None


async def init_oauth_state() -> OAuthStateStore | None:
    """Open the one-time OAuth state store, or nothing if OAuth is off."""
    global oauth_state_store
    if not YANDEX_OAUTH_ENABLED:
        return None
    oauth_state_store = OAuthStateStore(redis_url=REDIS_URL, ttl=OAUTH_STATE_TTL)
    await oauth_state_store.connect()
    return oauth_state_store


async def close_oauth_state() -> None:
    global oauth_state_store
    if oauth_state_store is not None:
        await oauth_state_store.close()
        oauth_state_store = None
