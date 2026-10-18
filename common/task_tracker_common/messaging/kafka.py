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

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
        try:
            await asyncio.wait_for(
                self._producer.send_and_wait(
                    self._topic,
                    key=key.encode("utf-8"),
                    value=json.dumps(event.model_dump(mode="json")).encode("utf-8"),
                ),
                timeout=_PUBLISH_TIMEOUT,
            )
        except (KafkaError, TimeoutError) as e:
            # A dropped notification must not fail the write that caused it.
            logger.warning(f"Event publish failed (ignored): {e}")
