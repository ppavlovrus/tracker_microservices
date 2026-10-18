"""The whole point of the tracing setup: one trace from HTTP to SQL.

Sends a request with a trace id of its own choosing, then asks Jaeger what
it collected for that id. If the chain is wired, the answer contains spans
from more than one process -- the gateway's request span and the worker's
command span -- and the command span is a child of the request span rather
than a root of an unrelated trace.

Needs the compose stand with Jaeger (JAEGER_URL, default
http://localhost:16686) and the gateway (BASE_URL).
"""

import asyncio
import os
import secrets
import time

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
JAEGER_URL = os.getenv("JAEGER_URL", "http://localhost:16686")


def _own_traceparent() -> str:
    """A valid W3C traceparent naming a trace id only this test knows.

    Choosing the id is what makes the check below deterministic: the trace
    we ask Jaeger about cannot be anyone else's.
    """
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def _services(trace: dict) -> set[str]:
    """The process names a trace's spans belong to."""
    processes = trace["processes"]
    return {processes[span["processID"]]["serviceName"] for span in trace["spans"]}


async def _trace_from_jaeger(traceparent: str) -> dict:
    """Poll Jaeger until the whole chain arrives; the exporter ships in batches.

    The gateway's batch and the worker's batch are separate, and either half
    can land first: the poll waits for both, not just for any data. A 404 is
    Jaeger's "not collected yet".
    """
    trace_id = traceparent.split("-")[1]
    deadline = time.monotonic() + 30.0
    async with httpx.AsyncClient(base_url=JAEGER_URL, trust_env=False) as jaeger:
        while time.monotonic() < deadline:
            response = await jaeger.get(f"/api/traces/{trace_id}")
            if response.status_code == 404:
                await asyncio.sleep(1.0)
                continue
            assert response.status_code == 200, response.text
            data = response.json().get("data") or []
            trace = data[0] if data else None
            if trace is not None and {"tracker-gateway", "tracker-tasks"} <= _services(trace):
                return trace
            await asyncio.sleep(1.0)
    pytest.fail(f"Jaeger never received the full chain for trace {trace_id}")


async def test_one_request_is_one_trace_from_http_to_sql():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, trust_env=False) as client:
        login = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200, login.text

        traceparent = _own_traceparent()
        created = await client.post(
            "/tasks",
            json={"title": "trace probe", "creator_id": 1},
            headers={"traceparent": traceparent},
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        await client.delete(f"/tasks/{task_id}")

    trace = await _trace_from_jaeger(traceparent)

    spans = trace["spans"]
    processes = trace["processes"]
    services = _services(trace)

    # The chain crosses processes: the edge that served the request and the
    # worker that ran the command are in the same trace.
    assert "tracker-gateway" in services, f"services in trace: {services}"
    assert "tracker-tasks" in services, f"services in trace: {services}"

    assert any(span["operationName"] == "POST /tasks" for span in spans)
    command_span = next(span for span in spans if span["operationName"] == "command create_task")

    # The link itself: the worker's span hangs off a span of the gateway,
    # not off nothing. Before the bus carried a traceparent this was two
    # unrelated traces, with the DB spans orphaned in the worker's.
    parents = {ref["spanID"] for ref in command_span.get("references", []) if ref["refType"] == "CHILD_OF"}
    gateway_span_ids = {
        span["spanID"]
        for span in spans
        if processes[span["processID"]]["serviceName"] == "tracker-gateway"
    }
    assert parents & gateway_span_ids

    # And the command reached the database: besides the command span, the
    # worker's part of the trace holds the query spans of the transaction
    # (BEGIN, INSERT, COMMIT), not just the command span alone.
    worker_spans = [
        span
        for span in spans
        if processes[span["processID"]]["serviceName"] == "tracker-tasks"
    ]
    assert len(worker_spans) >= 2, [span["operationName"] for span in worker_spans]


async def test_the_trace_reaches_the_sse_consumer_through_the_topic():
    """The same trace, continued through Kafka: HTTP -> bus -> SQL -> topic -> consumer.

    The producer injects the command span into the message headers; the
    consumer opens its span as that span's child, so the notification leg --
    which no HTTP request ever waits for -- still lands inside the trace the
    request started.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, trust_env=False) as client:
        login = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200, login.text

        traceparent = _own_traceparent()
        created = await client.post(
            "/tasks",
            json={"title": "kafka trace probe", "creator_id": 1},
            headers={"traceparent": traceparent},
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        await client.delete(f"/tasks/{task_id}")

    # The consume span arrives in the gateway's batch, the command span in
    # the worker's -- either can land first, so the poll waits for BOTH
    # before judging the parent link (the same lesson the first test here
    # learned about half-arrived traces).
    trace_id = traceparent.split("-")[1]
    deadline = time.monotonic() + 30.0
    trace = None

    def _complete(candidate: dict) -> bool:
        names = {span["operationName"] for span in candidate["spans"]}
        processes = candidate["processes"]
        services = {processes[span["processID"]]["serviceName"] for span in candidate["spans"]}
        return "consume task.created" in names and "tracker-tasks" in services

    async with httpx.AsyncClient(base_url=JAEGER_URL, trust_env=False) as jaeger:
        while time.monotonic() < deadline:
            response = await jaeger.get(f"/api/traces/{trace_id}")
            if response.status_code == 404:
                await asyncio.sleep(1.0)
                continue
            data = response.json().get("data") or []
            trace = data[0] if data else None
            if trace is not None and _complete(trace):
                break
            await asyncio.sleep(1.0)
    assert trace is not None, f"Jaeger never received trace {trace_id}"
    assert _complete(trace), "The trace never carried both the worker and the consumer halves"

    spans = trace["spans"]
    processes = trace["processes"]
    consume_span = next(s for s in spans if s["operationName"] == "consume task.created")

    # The consumer's span belongs to the gateway, and hangs off a span of the
    # worker -- the command span whose context the producer carried over.
    assert processes[consume_span["processID"]]["serviceName"] == "tracker-gateway"
    parents = {ref["spanID"] for ref in consume_span.get("references", []) if ref["refType"] == "CHILD_OF"}
    worker_span_ids = {
        s["spanID"] for s in spans if processes[s["processID"]]["serviceName"] == "tracker-tasks"
    }
    assert parents & worker_span_ids
