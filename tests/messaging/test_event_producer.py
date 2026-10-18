"""The best-effort contract of the event leg: writes survive a dead broker.

An event is an announcement, not a duty: losing one may grey out a
notification, but it must never fail, slow down, or corrupt the write that
caused it. The swallow lives inside ``EventProducer.publish`` -- that is the
boundary -- so these tests drive the real producer with an exploding send
and the real handler on top of it. No Kafka, no stack.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from aiokafka.errors import KafkaError
from task_tracker_common.contracts.commands import TaskCreationContract
from task_tracker_common.events import TaskEvent, TaskEventType
from task_tracker_common.messaging import kafka as kafka_module
from task_tracker_common.messaging.kafka import EventProducer
from tracker_tasks.handlers.task_handlers import TaskHandlers


class _ExplodingSend:
    """A started producer whose every send fails: the broker is on fire."""

    async def send_and_wait(self, *args, **kwargs):
        raise KafkaError("broker unreachable")

    async def stop(self) -> None:
        pass


class _StubRepository:
    """Just enough repository for a create: the stored row, complete enough
    for the answer contract to accept it."""

    async def create(self, data):
        now = datetime.now(UTC)
        return {
            "id": 7,
            "title": data["title"],
            "description": None,
            "status_id": data["status_id"],
            "creator_id": data["creator_id"],
            "deadline_start": None,
            "deadline_end": None,
            "created_at": now,
            "updated_at": now,
        }


async def test_publish_without_start_is_a_noop():
    producer = EventProducer("localhost:9092", "task.events")
    event = TaskEvent.now(TaskEventType.CREATED, 7, {"task": {"id": 7}})

    # No raise, no error: there is nobody to tell, so there is nothing to do.
    await producer.publish(event, key="7")


async def test_a_write_still_succeeds_when_the_announcement_fails():
    producer = EventProducer("localhost:9092", "task.events")
    producer._producer = _ExplodingSend()

    handlers = TaskHandlers(_StubRepository(), producer)
    command = TaskCreationContract(
        title="probe", description=None, status_id=1, creator_id=1, deadline_start=None, deadline_end=None
    )

    answer = await handlers.handle_create_task(command)

    # The write succeeded: the answer is the stored task, not the fire.
    assert answer["success"] is True
    assert answer["data"]["id"] == 7
    assert answer["data"]["tags"] == []


async def test_a_cancelled_startup_stops_the_half_started_producer(monkeypatch):
    """A startup timeout must not leak the bootstrap connection."""
    stopped = []

    class _CancelledStart:
        async def start(self):
            raise asyncio.CancelledError()

        async def stop(self):
            stopped.append(True)

    monkeypatch.setattr(kafka_module, "AIOKafkaProducer", lambda *args, **kwargs: _CancelledStart())
    producer = EventProducer("localhost:9092", "task.events")

    with pytest.raises(asyncio.CancelledError):
        await producer.start()

    assert stopped, "the half-started producer was left running"
