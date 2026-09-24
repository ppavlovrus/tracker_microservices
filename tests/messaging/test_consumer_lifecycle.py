"""How a worker consumes, and how it stops.

Two questions the mentor's point about ``asyncio.Task`` actually asks. Are
handlers concurrent, or does one slow command block the queue behind it? And
what happens to a handler that is halfway through its work when the service is
asked to stop?

These talk to the RabbitMQ the compose stack runs; they declare their own
throwaway queues and delete them again.
"""

import asyncio
import json
import os
import uuid

import aio_pika
import pytest
from task_tracker_common.messaging import RabbitMQClient

AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/")


@pytest.fixture
async def consumer():
    """A connected client whose queue is deleted when the test ends."""
    client = RabbitMQClient(amqp_url=AMQP_URL, service_name="test-consumer")
    await client.connect()
    queue_name = f"test.lifecycle.{uuid.uuid4().hex[:10]}"

    yield client, queue_name

    await client.stop_consuming(drain_timeout=5.0)
    queue = await client.channel.declare_queue(name=queue_name, durable=True, auto_delete=False)
    await queue.delete(if_unused=False, if_empty=False)
    await client.close()


async def publish(queue_name: str, payloads: list[dict]) -> None:
    """Drop messages on the queue with nobody waiting for an answer."""
    connection = await aio_pika.connect_robust(AMQP_URL)
    async with connection:
        channel = await connection.channel()
        for payload in payloads:
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(payload).encode()),
                routing_key=queue_name,
            )


async def test_handlers_of_one_queue_run_at_the_same_time(consumer):
    """aio_pika gives every delivery its own task, so slow commands overlap.

    Without that, three handlers sleeping 300ms would take 900ms in a row and
    one slow command would hold up everything behind it.
    """
    client, queue_name = consumer
    running = 0
    peak = 0
    handled = asyncio.Event()
    done = []

    async def handler(payload, message):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.3)
        running -= 1
        done.append(payload["n"])
        if len(done) == 3:
            handled.set()
        return {"success": True}

    await client.consume(queue_name=queue_name, callback=handler, prefetch_count=10)
    await publish(queue_name, [{"n": 1}, {"n": 2}, {"n": 3}])

    await asyncio.wait_for(handled.wait(), timeout=5)

    assert sorted(done) == [1, 2, 3]
    assert peak >= 2, f"handlers never overlapped (peak={peak}): the queue is serialised"


async def test_stopping_waits_for_a_handler_in_flight(consumer):
    """Closing the connection under a running handler is what this prevents."""
    client, queue_name = consumer
    started = asyncio.Event()
    release = asyncio.Event()
    finished = []

    async def handler(payload, message):
        started.set()
        await release.wait()
        finished.append(payload["n"])
        return {"success": True}

    await client.consume(queue_name=queue_name, callback=handler, prefetch_count=10)
    await publish(queue_name, [{"n": 1}])
    await asyncio.wait_for(started.wait(), timeout=5)

    stopping = asyncio.create_task(client.stop_consuming(drain_timeout=5.0))
    await asyncio.sleep(0.2)

    assert not stopping.done(), "shutdown did not wait for the handler still running"
    assert finished == [], "the handler finished on its own, so nothing was proven"

    release.set()
    await asyncio.wait_for(stopping, timeout=5)

    assert finished == [1], "shutdown returned before the handler had finished"


async def test_stopping_takes_no_new_messages(consumer):
    """The broker redelivers what was never acknowledged, so refusing is safe."""
    client, queue_name = consumer
    handled = []

    async def handler(payload, message):
        handled.append(payload["n"])
        return {"success": True}

    await client.consume(queue_name=queue_name, callback=handler, prefetch_count=10)
    await publish(queue_name, [{"n": 1}])
    await asyncio.sleep(0.5)
    assert handled == [1]

    await client.stop_consuming(drain_timeout=5.0)

    await publish(queue_name, [{"n": 2}])
    await asyncio.sleep(0.5)

    assert handled == [1], "a message arrived after the consumer was cancelled"


async def test_the_command_travels_in_a_header_too(consumer):
    """Nothing routes on it yet; it is there to be readable without the body."""
    client, queue_name = consumer
    seen = {}

    async def handler(payload, message):
        seen["headers"] = dict(message.headers or {})
        seen["payload"] = payload
        return {"success": True}

    await client.consume(queue_name=queue_name, callback=handler, prefetch_count=10)

    caller = RabbitMQClient(amqp_url=AMQP_URL, service_name="test-caller")
    await caller.connect()
    await caller.setup_rpc_client()
    try:
        answer = await caller.call(queue_name=queue_name, message={"command": "do_a_thing", "data": {}}, timeout=5)
    finally:
        await caller.close()

    assert answer == {"success": True}
    assert seen["headers"].get("command") == "do_a_thing"
    # The body still carries it: the payload stays the single source of truth.
    assert seen["payload"]["command"] == "do_a_thing"
