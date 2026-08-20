"""Server-Sent Events endpoint for live task notifications.

One-way stream (server -> browser) delivering task events as they happen:

    event: task.created            (also task.updated / task.deleted)
    data: {"type": "task.created", "task": {...}, "ts": "..."}

Between events the server emits a ``: keep-alive`` comment every
SSE_HEARTBEAT_INTERVAL seconds so idle connections survive proxies and a
vanished client is noticed on the next write attempt.

Auth: the HTTP auth middleware only guards writes, so the session cookie is
checked here explicitly and the stream is refused (401) to guests -- task
notifications are for logged-in users only.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ...config import SESSION_COOKIE_NAME, SSE_HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sse"])

# Set in main.py lifespan.
events_hub = None
session_store = None


def set_events_hub(hub) -> None:
    global events_hub
    events_hub = hub


def set_session_store(store) -> None:
    global session_store
    session_store = store


async def _event_stream() -> AsyncGenerator[str, None]:
    """Yield SSE frames from the hub queue, with periodic keep-alives."""
    queue = events_hub.subscribe()
    try:
        # A comment on connect flushes headers so the browser fires `onopen`.
        yield ": connected\n\n"
        while True:
            try:
                raw = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL)
            except TimeoutError:
                # Silence: probe the connection. A dead client raises on the
                # next send and the generator is closed by StreamingResponse.
                yield ": keep-alive\n\n"
                continue

            try:
                event_type = json.loads(raw).get("type", "message")
            except (ValueError, TypeError):
                logger.warning("Corrupt event payload, skipping")
                continue
            yield f"event: {event_type}\ndata: {raw}\n\n"
    finally:
        events_hub.unsubscribe(queue)


@router.get("/sse/tasks")
async def sse_tasks(request: Request):
    """Authenticated SSE stream of task events."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = await session_store.get(token) if (session_store and token) else None
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    if events_hub is None or not events_hub.available:
        return JSONResponse(status_code=503, content={"detail": "Notifications unavailable"})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering (nginx) so events are not held back.
            "X-Accel-Buffering": "no",
        },
    )
