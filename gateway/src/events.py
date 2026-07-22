"""Redis-backed hub for Server-Sent task events.

Write routers publish task events (created/updated/deleted) to a Redis
channel; every gateway instance subscribes to that channel and fans each
event out to its local SSE connections, so notifications keep working when
the gateway is scaled horizontally.

Two deliberate differences from the chat hub:

* Events are ephemeral. There is no history list and nothing is replayed on
  connect -- a notification only matters live, and stale ones would just be
  noise on the board.
* Publishing is best-effort. A task write must succeed even when the event
  cannot be delivered, so ``publish`` swallows Redis errors and never raises
  into the request path.

Each SSE connection owns a bounded ``asyncio.Queue``. A client that cannot
keep up has its oldest events dropped rather than being allowed to grow the
gateway's memory without bound.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# How long to wait before re-subscribing after a pub/sub failure.
_LISTENER_RETRY_DELAY = 2.0


class EventsHub:
    """Fan task events out to local SSE streams via Redis pub/sub."""

    def __init__(self, redis_url: str, channel: str, max_queue: int):
        self._redis_url = redis_url
        self._channel = channel
        self._max_queue = max_queue
        self._client: Optional[aioredis.Redis] = None
        self._queues: Set[asyncio.Queue] = set()

    @property
    def available(self) -> bool:
        """True when Redis is reachable and the hub can serve clients."""
        return self._client is not None

    async def connect(self) -> None:
        """Open the connection and ping. On failure the hub stays down."""
        client = aioredis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
        )
        try:
            await client.ping()
        except RedisError as e:
            logger.warning(f"Redis unavailable, events hub down: {e}")
            await client.aclose()
            return

        self._client = client
        logger.info(f"Events hub connected: channel={self._channel}")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- local subscribers -------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE connection and return its event queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._queues.add(queue)
        logger.info(f"SSE client subscribed ({len(self._queues)} online)")
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)
        logger.info(f"SSE client unsubscribed ({len(self._queues)} online)")

    # -- publishing --------------------------------------------------------

    async def publish(self, event: Dict[str, Any]) -> None:
        """Broadcast an event via pub/sub. Best-effort: never raises."""
        if self._client is None:
            return
        try:
            await self._client.publish(self._channel, json.dumps(event))
        except RedisError as e:
            # A dropped notification must not fail the task write that caused it.
            logger.warning(f"Event publish failed (ignored): {e}")

    # -- pub/sub listener --------------------------------------------------

    async def run_listener(self) -> None:
        """Subscribe to the channel and fan events out to local queues.

        Runs for the lifetime of the app (one task per gateway instance) and
        re-subscribes after transient Redis failures.
        """
        while True:
            if self._client is None:
                await asyncio.sleep(_LISTENER_RETRY_DELAY)
                await self.connect()
                continue
            try:
                async with self._client.pubsub() as pubsub:
                    await pubsub.subscribe(self._channel)
                    async for item in pubsub.listen():
                        if item["type"] == "message":
                            self._fan_out(item["data"])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # A dead listener means events are accepted but never delivered.
                logger.warning(f"Events listener dropped, retrying: {e}")
                await asyncio.sleep(_LISTENER_RETRY_DELAY)

    def _fan_out(self, raw: str) -> None:
        """Push a raw JSON payload into every local queue, dropping if full."""
        # Snapshot: queues may (un)subscribe while we iterate.
        for queue in list(self._queues):
            try:
                queue.put_nowait(raw)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest event to make room and keep
                # the stream flowing rather than blocking every other client.
                try:
                    queue.get_nowait()
                    queue.put_nowait(raw)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    logger.debug("Dropped event for a slow SSE client")
