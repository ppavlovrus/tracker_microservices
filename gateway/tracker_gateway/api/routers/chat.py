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
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...core.config import (
    CHAT_HEARTBEAT_INTERVAL,
    CHAT_HEARTBEAT_TIMEOUT,
    CHAT_MAX_MESSAGE_LENGTH,
    SESSION_COOKIE_NAME,
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
        "ts": datetime.now(UTC).isoformat(),
    }


class _FrameRejectedError(Exception):
    """The frame goes nowhere and the client is told why."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _frame_text(frame: dict) -> str | None:
    """The text a message frame carries, or None when there is nothing to send."""
    text = (frame.get("text") or "").strip()
    if not text:
        return None
    if len(text) > CHAT_MAX_MESSAGE_LENGTH:
        raise _FrameRejectedError("Message too long")
    return text


def _message_text(raw: str) -> str | None:
    """Decode one client frame and return the text it wants published.

    None means the frame is legitimately silent -- a heartbeat pong or an
    empty message. A frame the client got wrong raises instead, carrying the
    wording that goes back over the socket.
    """
    try:
        frame = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise _FrameRejectedError("Invalid JSON") from exc

    kind = frame.get("type")
    if kind == "pong":
        return None
    if kind != "message":
        raise _FrameRejectedError("Unknown frame type")

    return _frame_text(frame)


async def _handle_frame(websocket: WebSocket, user: dict, raw: str) -> None:
    """Process one client frame: publish a message or ignore a pong."""
    try:
        text = _message_text(raw)
    except _FrameRejectedError as e:
        await websocket.send_json({"type": "error", "detail": e.detail})
        return

    if text is None:
        return

    if not await chat_hub.publish(_build_message(user, text)):
        await websocket.send_json({"type": "error", "detail": "Chat unavailable"})


async def _authenticate(websocket: WebSocket) -> dict | None:
    """Return the session behind the cookie, closing the socket if there is none."""
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = await session_store.get(token) if (session_store and token) else None
    if user is None:
        await websocket.close(code=4401, reason="Authentication required")
    return user


async def _receive_loop(websocket: WebSocket, user: dict) -> None:
    """Read frames until the peer goes away or stops answering pings."""
    last_seen = time.monotonic()

    while True:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=CHAT_HEARTBEAT_INTERVAL)
        except TimeoutError:
            # Silence. Either probe the peer or give up on it.
            if time.monotonic() - last_seen > CHAT_HEARTBEAT_TIMEOUT:
                logger.info(f"Chat heartbeat timeout: user={user['username']}")
                await websocket.close(code=1001, reason="Heartbeat timeout")
                return
            await websocket.send_json({"type": "ping"})
            continue

        last_seen = time.monotonic()
        await _handle_frame(websocket, user, raw)


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    """Authenticated chat connection: history replay, then receive loop."""
    # The HTTP auth middleware does not apply to WebSockets, so the session
    # cookie is checked here explicitly. Accept first: a close before accept
    # surfaces as a bare HTTP 403 with no close code for the client to act on.
    await websocket.accept()

    user = await _authenticate(websocket)
    if user is None:
        return

    if chat_hub is None or not chat_hub.available:
        await websocket.close(code=1013, reason="Chat backend unavailable")
        return

    await websocket.send_json({"type": "history", "messages": await chat_hub.history()})
    chat_hub.register(websocket)

    try:
        await _receive_loop(websocket, user)
    except WebSocketDisconnect:
        pass
    finally:
        chat_hub.unregister(websocket)
