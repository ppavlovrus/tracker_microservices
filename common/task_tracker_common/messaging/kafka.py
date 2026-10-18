"""Kafka producer for the event leg: facts, not commands.

``RabbitMQClient`` moves commands -- request-reply, one answer, and the
message is gone once the caller has it. This client moves facts: a task was
created, updated, deleted. An event stays in the log for its retention
whether anybody has read it, every consumer group reads its own copy, and
nobody answers. Two brokers, two jobs: the RPC bus keeps the commands, this
keeps the notifications.

Publishing is best-effort, the same contract the gateway's Redis hub had: a
dropped notification must not fail the write that caused it, so ``publish``
logs and swallows instead of raising. ``acks="all"`` underneath means the
broker confirms a write only after every in-sync replica has it -- on this
single-node stand that is a promise about the broker's own disk, and it is
the knob to revisit the day the answer to "may we lose an event?" changes.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# A proxy until setup_telemetry installs the real provider; spans started
# before that are no-ops, so the bus traces with or without telemetry.
tracer = trace.get_tracer(__name__)

# An event may not hold the write hostage. A broker that died after the
# producer connected makes send_and_wait retry for minutes -- measured: a
# dead broker turned every write into a 30-second RPC timeout. Bounded here,
# the sender may still deliver the batch afterwards (at-least-once), which
# an announcement tolerates.
_PUBLISH_TIMEOUT = 5.0


class EventProducer:
    """Publishes JSON events to one topic, keyed for per-entity ordering."""

    def __init__(self, bootstrap_servers: str, topic: str) -> None:
        """Remember the address and the topic; nothing connects yet."""
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Connect and learn the cluster layout. On failure, stays down.

        A producer that cannot start stays inert: the worker still serves
        commands, it just announces nothing -- degraded, the same way the
        events hub degrades when Redis is down.
        """
        producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers, acks="all")
        try:
            await producer.start()
        except KafkaError as e:
            logger.warning(f"Kafka unavailable, events will not be published: {e}")
            await producer.stop()
            return
        except BaseException:
            # A startup timeout cancels start() mid-flight: stop the
            # half-started producer, or its bootstrap connection and
            # metadata task leak for the life of the process. The cancel
            # itself keeps travelling -- the worker serves on without events.
            await producer.stop()
            raise

        self._producer = producer
        logger.info(f"Event producer ready: topic={self._topic}")

    async def stop(self) -> None:
        """Flush whatever is in flight, then close. Safe to call twice."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            logger.info("Event producer stopped")

    async def publish(self, event: BaseModel, key: str) -> None:
        """Send one event, best-effort: never raises into the caller.

        The event is a pydantic model and this is the wire boundary, so the
        JSON dump happens here in ``mode="json"`` -- dates become strings at
        the same door they leave through, the lesson ``rpc_ok`` already
        taught the command bus.

        ``key`` decides the partition: same key, same partition, and events
        for one entity arrive in the order they were sent. A keyless send
        would round-robin, and "updated" could overtake "created".
        """
        if self._producer is None:
            return

        # The current span travels as a traceparent header, the same way it
        # crosses the RabbitMQ leg: the consumer continues this trace instead
        # of starting an unrelated one.
        carrier: dict[str, str] = {}
        propagate.inject(carrier)
        headers = [(name, value.encode("utf-8")) for name, value in carrier.items()]

        try:
            await asyncio.wait_for(
                self._producer.send_and_wait(
                    self._topic,
                    key=key.encode("utf-8"),
                    value=json.dumps(event.model_dump(mode="json")).encode("utf-8"),
                    headers=headers,
                ),
                timeout=_PUBLISH_TIMEOUT,
            )
        except (KafkaError, TimeoutError) as e:
            # A dropped notification must not fail the write that caused it.
            logger.warning(f"Event publish failed (ignored): {e}")


# How long to wait before rejoining after the broker goes away mid-stream.
_REJOIN_DELAY = 2.0


class EventConsumer:
    """Reads JSON events from one topic as one group, for the process's life.

    A consumer group is a bookmark: every group reads its own copy of the
    log, and its committed offset says where it stopped. That is why each
    consumer instance invents its own group id -- a notification board needs
    every event on every instance (broadcast), while one shared group would
    split the log between instances (load balancing) and every second client
    would miss half the notifications. ``auto_offset_reset="latest"`` keeps
    the old ephemeral policy: a fresh group starts at the tip, and a
    reconnecting instance does not replay history at the board.
    """

    def __init__(self, bootstrap_servers: str, topic: str, group_id: str) -> None:
        """Remember the address, topic and group; nothing connects yet."""
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None

    @property
    def started(self) -> bool:
        """True once the group is joined and events can arrive."""
        return self._consumer is not None

    async def start(self) -> bool:
        """Join the group. False when the broker is unreachable."""
        consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="latest",
        )
        try:
            await consumer.start()
        except KafkaError as e:
            logger.warning(f"Kafka consumer could not join ({self._group_id}): {e}")
            await consumer.stop()
            return False
        except BaseException:
            # Mirror EventProducer.start: a cancel mid-join must stop the
            # half-started consumer, or its bootstrap connection leaks.
            await consumer.stop()
            raise

        self._consumer = consumer
        logger.info(f"Event consumer joined: topic={self._topic}, group={self._group_id}")
        return True

    async def stop(self) -> None:
        """Leave the group, committing what was read. Safe to call twice."""
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Event consumer stopped")

    async def run(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Poll forever, handing each decoded event to ``handler``.

        A message that does not parse is logged and skipped: one poison
        payload must not stall the board behind it. A broker that goes away
        mid-stream drops the consumer out of the loop -- it sleeps, rejoins,
        and continues from the committed offset.
        """
        while True:
            if self._consumer is None and not await self.start():
                await asyncio.sleep(_REJOIN_DELAY)
                continue
            try:
                async for message in self._consumer:
                    await self._dispatch(message, handler)
            except KafkaError as e:
                logger.warning(f"Event consumer dropped, rejoining: {e}")
                await self.stop()
                await asyncio.sleep(_REJOIN_DELAY)
            except Exception as e:
                # Same contract the Redis listener had: any unexpected error
                # rejoins instead of killing the leg. CancelledError passes.
                logger.warning(f"Event consumer crashed, rejoining: {e!r}")
                await self.stop()
                await asyncio.sleep(_REJOIN_DELAY)

    async def _dispatch(self, message, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Decode one message and run the handler inside the trace it carries."""
        if message.value is None:
            # A tombstone (compaction delete marker): no fact to tell.
            logger.warning("Event has no value (tombstone), skipping")
            return

        try:
            event = json.loads(message.value.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            logger.warning("Event does not parse as JSON, skipping")
            return

        # The producer's span arrives in the headers; the handler runs inside
        # its continuation, so the trace that started at the HTTP edge now
        # reaches the SSE leg too.
        extracted = {name: value.decode("utf-8") for name, value in (message.headers or [])}
        context = propagate.extract(extracted)
        name = f"consume {event.get('type', 'event')}"
        with tracer.start_as_current_span(name, context=context, kind=SpanKind.CONSUMER):
            await handler(event)
