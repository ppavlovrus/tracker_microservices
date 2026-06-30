"""Token-bucket rate limiter for the Gateway, backed by Redis.

Each client IP gets a bucket of ``capacity`` tokens that refills at
``refill_rate`` tokens/second. Every request consumes one token; when the
bucket is empty the request is rejected with HTTP 429.

The whole read-refill-consume cycle runs inside a single Lua script so it is
atomic across concurrent requests and costs one Redis round-trip. Server time
is taken from ``redis.call('TIME')`` so multiple gateway replicas stay
consistent regardless of their local clocks.

Like the cache, the limiter is best-effort and **fails open**: if Redis is
unreachable the request is allowed through rather than blocked -- a rate
limiter must never become a self-inflicted outage.
"""

import logging
from typing import Optional, Tuple

from redis import asyncio as aioredis
from redis.exceptions import RedisError

from .metrics import RATE_LIMIT_DECISIONS

logger = logging.getLogger(__name__)

# KEYS[1]            = bucket key (rl:<ip>)
# ARGV[1]=capacity, ARGV[2]=refill_rate, ARGV[3]=requested
# Returns {allowed(0|1), tokens_left(str), retry_after_seconds(str)}.
# tokens/retry_after are returned as strings to preserve fractional values
# (Redis truncates Lua numbers to integers on the way back).
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])

local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000.0

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
    tokens = capacity
    ts = now
end

local delta = now - ts
if delta < 0 then delta = 0 end
tokens = math.min(capacity, tokens + delta * rate)

local allowed = 0
if tokens >= requested then
    allowed = 1
    tokens = tokens - requested
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Drop an idle bucket once it would be fully refilled (plus a small margin).
local ttl = math.ceil(capacity / rate) + 1
redis.call('PEXPIRE', key, ttl * 1000)

local retry_after = 0
if allowed == 0 then
    retry_after = (requested - tokens) / rate
end

return {allowed, tostring(tokens), tostring(retry_after)}
"""


class RateLimiter:
    """Per-IP token-bucket limiter backed by a Redis Lua script."""

    def __init__(
        self,
        redis_url: str,
        capacity: int,
        refill_rate: float,
        enabled: bool = True,
    ):
        self._redis_url = redis_url
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._enabled = enabled
        self._client: Optional[aioredis.Redis] = None
        self._script = None

    async def connect(self) -> None:
        """Open the connection and register the Lua script. Fails open."""
        if not self._enabled:
            logger.info("Rate limiting disabled via config")
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
            logger.warning(f"Redis unavailable, rate limiting disabled: {e}")
            await client.aclose()
            return

        self._client = client
        self._script = client.register_script(_TOKEN_BUCKET_LUA)
        logger.info(
            f"Rate limiter connected: capacity={self.capacity}, "
            f"refill={self.refill_rate}/s"
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def check(self, ip: str) -> Tuple[bool, int, float]:
        """Consume one token for ``ip``.

        Returns ``(allowed, remaining, retry_after_seconds)``. On any Redis
        error the request is allowed through (fail-open).

        Decisions are recorded on ``gateway_rate_limit_decisions_total``. A
        disabled limiter records nothing -- it is not making decisions.
        """
        if self._client is None:
            return True, self.capacity, 0.0
        try:
            allowed, tokens, retry_after = await self._script(
                keys=[f"rl:{ip}"],
                args=[self.capacity, self.refill_rate, 1],
            )
        except RedisError as e:
            logger.warning(f"Rate limit check failed for {ip}, allowing: {e}")
            RATE_LIMIT_DECISIONS.labels(decision="failopen").inc()
            return True, self.capacity, 0.0

        is_allowed = bool(int(allowed))
        RATE_LIMIT_DECISIONS.labels(
            decision="allowed" if is_allowed else "blocked"
        ).inc()
        return is_allowed, int(float(tokens)), float(retry_after)
