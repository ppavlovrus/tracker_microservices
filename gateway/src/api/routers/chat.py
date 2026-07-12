"""WebSocket chat endpoint.

Protocol (JSON frames):
  server -> client: {"type": "history", "messages": [...]}   on connect
                    {"type": "message", id, user_id, username, text, ts}
                    {"type": "ping"}                          heartbeat probe
                    {"type": "error", "detail": "..."}
  client -> server: {"type": "message", "text": "..."}
                    {"type": "pong"}                          heartbeat reply

Heartbeat: the server sends a ping whenever the connection has been silent
for CHAT_HEARTBEAT_INTERVAL seconds. Any client frame (pong or message)
counts as liveness; a connection silent for CHAT_HEARTBEAT_TIMEOUT seconds
is closed so dead peers behind NAT/proxies do not pile up.

Close codes: 4401 unauthenticated, 1013 chat backend unavailable.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...config import (
    SESSION_COOKIE_NAME,
    CHAT_HEARTBEAT_INTERVAL,
    CHAT_HEARTBEAT_TIMEOUT,
    CHAT_MAX_MESSAGE_LENGTH,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Set in main.py lifespan.
chat_hub = None
session_store = None


def set_chat_hub(hub) -> None:
    global chat_hub
    chat_hub = hub


def set_session_store(store) -> None:
    global session_store
    session_store = store


def _build_message(user: dict, text: str) -> dict:
    return {
        "type": "message",
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "username": user["username"],
        "text": text,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def _handle_frame(websocket: WebSocket, user: dict, raw: str) -> None:
    """Process one client frame: publish a message or ignore a pong."""
    try:
        frame = json.loads(raw)
    except (ValueError, TypeError):
        await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
        return

    kind = frame.get("type")
    if kind == "pong":
        return
    if kind != "message":
        await websocket.send_json({"type": "error", "detail": "Unknown frame type"})
        return

    text = (frame.get("text") or "").strip()
    if not text:
        return
    if len(text) > CHAT_MAX_MESSAGE_LENGTH:
        await websocket.send_json({"type": "error", "detail": "Message too long"})
        return

    if not await chat_hub.publish(_build_message(user, text)):
        await websocket.send_json({"type": "error", "detail": "Chat unavailable"})


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    """Authenticated chat connection: history replay, then receive loop."""
    # The HTTP auth middleware does not apply to WebSockets, so the session
    # cookie is checked here explicitly. Accept first: a close before accept
    # surfaces as a bare HTTP 403 with no close code for the client to act on.
    await websocket.accept()

    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = await session_store.get(token) if (session_store and token) else None
    if user is None:
        await websocket.close(code=4401, reason="Authentication required")
        return

    if chat_hub is None or not chat_hub.available:
        await websocket.close(code=1013, reason="Chat backend unavailable")
        return

    await websocket.send_json({"type": "history", "messages": await chat_hub.history()})
    chat_hub.register(websocket)
    last_seen = time.monotonic()

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=CHAT_HEARTBEAT_INTERVAL
                )
            except asyncio.TimeoutError:
                # Silence. Either probe the peer or give up on it.
                if time.monotonic() - last_seen > CHAT_HEARTBEAT_TIMEOUT:
                    logger.info(f"Chat heartbeat timeout: user={user['username']}")
                    await websocket.close(code=1001, reason="Heartbeat timeout")
                    return
                await websocket.send_json({"type": "ping"})
                continue

            last_seen = time.monotonic()
            await _handle_frame(websocket, user, raw)
    except WebSocketDisconnect:
        pass
    finally:
        chat_hub.unregister(websocket)
