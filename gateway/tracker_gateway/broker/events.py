"""Kafka-fed hub for Server-Sent task events.

The tasks worker announces every write to the ``task.events`` topic; each
gateway instance reads the topic in its own consumer group and fans each
event out to its local SSE connections. A group is a bookmark: a group per
instance means every instance sees every event -- broadcast, which is what a
notification board wants. (One shared group would split the log between the
instances: load balancing, and every second client would miss half the
notifications.)

Two deliberate policies, carried over from the Redis hub this replaced:

* Events are live-only. A fresh group starts at the tip of the log
  (``auto_offset_reset="latest"``), nothing is replayed on connect -- a
  notification only matters now, and stale ones would just be noise on the
  board. The log still keeps an hour of history, so a replay stays possible
  the day that policy changes.
* Reading is best-effort, and so is arriving: a broker that is down leaves
  the hub unavailable (SSE answers 503) while everything else serves on,
  and it rejoins on its own when the broker returns.

Each SSE connection owns a bounded ``asyncio.Queue``. A client that cannot
keep up has its oldest events dropped rather than being allowed to grow the
gateway's memory without bound.
"""

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from task_tracker_common.events import TaskEvent
from task_tracker_common.messaging.kafka import EventConsumer

from ..core.config import KAFKA_BOOTSTRAP_URL, KAFKA_EVENTS_TOPIC, SSE_ENABLED, SSE_MAX_QUEUE

logger = logging.getLogger(__name__)


class EventsHub:
    """Fan task events out to local SSE streams, fed by Kafka."""

    def __init__(self, bootstrap_servers: str, topic: str, max_queue: int) -> None:
        """One consumer in a group of its own, plus the local queues."""
        # A group id per hub start is what makes this broadcast: each gateway
        # instance reads everything. Fixed per process, unique per start.
        self._consumer = EventConsumer(bootstrap_servers, topic, group_id=f"sse-{uuid4().hex}")
        self._max_queue = max_queue
        self._queues: set[asyncio.Queue] = set()

    @property
    def available(self) -> bool:
        """True when the consumer has joined and events can arrive."""
        return self._consumer.started

    async def close(self) -> None:
        """Leave the group; the queues belong to the SSE connections."""
        await self._consumer.stop()

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

    # -- the bridge --------------------------------------------------------

    async def run_listener(self) -> None:
        """Read the topic for the lifetime of the app and fan events out.

        The consumer joins (and rejoins) on its own; this wrapper exists so
        shutdown has one task to cancel, the shape the Redis listener had.
        """
        await self._consumer.run(self._deliver)

    async def _deliver(self, raw_event: dict[str, Any]) -> None:
        """Validate one event and flatten it onto the SSE wire.

        ``TaskEvent`` is the inter-service contract; the SSE wire format is
        the browser's, older than Kafka here: the payload's keys become the
        frame's keys, which is exactly the shape the Redis announcements
        sent. Off-contract events are logged and skipped -- a board must not
        stall on one bad message.
        """
        try:
            event = TaskEvent.model_validate(raw_event)
        except ValidationError:
            logger.warning("Event off-contract, skipping")
            return

        # The payload goes in first: unpacking it last would let a wire-side
        # payload key named "type" or "ts" overwrite the contract's own.
        frame = dict(event.payload)
        frame["type"] = event.type.value
        frame["ts"] = event.ts
        wire = json.dumps(frame)
        self._fan_out(wire)

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


# ── Lifecycle ────────────────────────────────────────────────

hub: EventsHub | None = None
listener_task: asyncio.Task | None = None


async def init_events() -> EventsHub | None:
    """Start the hub and its consumer, or nothing if SSE is off.

    The consumer joins inside the listener task, so a broker that is down at
    startup does not hold the gateway hostage: SSE answers 503 until the
    group is joined, everything else serves on.
    """
    global hub, listener_task
    if not SSE_ENABLED:
        return None
    hub = EventsHub(
        bootstrap_servers=KAFKA_BOOTSTRAP_URL,
        topic=KAFKA_EVENTS_TOPIC,
        max_queue=SSE_MAX_QUEUE,
    )
    listener_task = asyncio.create_task(hub.run_listener())
    return hub


async def close_events() -> None:
    """Stop the listener before the consumer it drives."""
    global hub, listener_task
    if listener_task is not None:
        listener_task.cancel()
        with suppress(asyncio.CancelledError):
            await listener_task
        listener_task = None
    if hub is not None:
        await hub.close()
        hub = None
