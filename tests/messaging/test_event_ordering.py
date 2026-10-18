"""The ordering guarantee the partition key buys: per-task, in-order, one lane.

Events for one task are keyed by the task id, and Kafka orders messages only
inside a partition, so same key = same partition = the order they were
written. This test drives a task through its lifecycle over the live API and
reads the topic back with a fresh consumer group -- from the beginning,
which the SSE leg never does -- asserting the events arrived as one ordered
run in one partition.

Needs the compose stand (BASE_URL) with Kafka (KAFKA_BOOTSTRAP, default
localhost:29092 -- the HOST listener).
"""

import asyncio
import json
import os
import time
from uuid import uuid4

import httpx
from aiokafka import AIOKafkaConsumer

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
TOPIC = os.getenv("KAFKA_EVENTS_TOPIC", "task.events")


async def _login_token(client: httpx.AsyncClient) -> str:
    response = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _read_events_for(task_id: int, deadline: float) -> list:
    """Consume the topic until the task's deleted event arrives (or deadline)."""
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=f"ordering-probe-{uuid4().hex}",
        auto_offset_reset="earliest",
    )
    collected: list[dict] = []
    await consumer.start()
    try:
        while time.monotonic() < deadline:
            try:
                message = await asyncio.wait_for(consumer.getone(), timeout=1.0)
            except TimeoutError:
                continue
            try:
                event = json.loads(message.value.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if event.get("task_id") == task_id:
                collected.append({**event, "_partition": message.partition})
            if event.get("task_id") == task_id and event.get("type") == "task.deleted":
                return collected
    finally:
        await consumer.stop()
    return collected


async def test_one_tasks_events_arrive_in_order_in_one_partition():
    probe = uuid4().hex[:8]
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, trust_env=False) as client:
        auth = {"Authorization": f"Bearer {await _login_token(client)}"}

        created = await client.post(
            "/tasks", json={"title": f"ordering probe {probe}", "creator_id": 1}, headers=auth
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]

        for i in range(3):
            renamed = await client.put(
                f"/tasks/{task_id}", json={"title": f"ordering probe {probe} #{i}"}, headers=auth
            )
            assert renamed.status_code == 200, renamed.text

        deleted = await client.delete(f"/tasks/{task_id}", headers=auth)
        assert deleted.status_code == 204, deleted.text

    events = await _read_events_for(task_id, deadline=time.monotonic() + 30.0)

    # The lifecycle as it happened, nothing skipped, nothing reordered.
    assert [e["type"] for e in events] == [
        "task.created",
        "task.updated",
        "task.updated",
        "task.updated",
        "task.deleted",
    ], [e["type"] for e in events]

    # One lane: the key put every event of this task into the same partition.
    # A keyless send would have round-robined them across all three.
    assert {e["_partition"] for e in events} == {events[0]["_partition"]}, [
        e["_partition"] for e in events
    ]
