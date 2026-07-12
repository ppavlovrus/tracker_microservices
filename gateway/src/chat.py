"""Redis-backed chat hub for the Gateway.

Live delivery uses Redis pub/sub: every gateway instance subscribes to one
channel and fans incoming messages out to its local WebSocket connections, so
the chat keeps working when the gateway is scaled horizontally. Pub/sub does
not persist anything, so recent history is kept separately in a capped Redis
LIST and replayed to clients on connect.

Like the session store, the hub fails closed: with Redis down, new chat
connections are refused instead of silently serving a chat that cannot
deliver messages across instances.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket
from redis import asyncio as aioredis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# How long to wait before re-subscribing after a pub/sub failure.
_LISTENER_RETRY_DELAY = 2.0


class ChatHub:
    """One chat room: pub/sub fan-out plus a capped history list."""

    def __init__(self, redis_url: str, channel: str, history_size: int):
        self._redis_url = redis_url
        self._channel = channel
        self._history_size = history_size
        self._client: Optional[aioredis.Redis] = None
        self._connections: Set[WebSocket] = set()

    @property
    def available(self) -> bool:
        """True when Redis is reachable and the hub can serve clients."""
        return self._client is not None

    @property
    def _history_key(self) -> str:
        return f"chat_history:{self._channel}"

    async def connect(self) -> None:
        """Open the connection and ping. On failure the hub stays down."""
        client = aioredis.from_url(
            self._redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
        )
        try:
            await client.ping()
        except RedisError as e:
            logger.warning(f"Redis unavailable, chat hub down: {e}")
            await client.aclose()
            return

        self._client = client
        logger.info(f"Chat hub connected: channel={self._channel}")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- local connections -------------------------------------------------

    def register(self, websocket: WebSocket) -> None:
        self._connections.add(websocket)
        logger.info(f"Chat client joined ({len(self._connections)} online)")

    def unregister(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info(f"Chat client left ({len(self._connections)} online)")

    # -- messages ----------------------------------------------------------

    async def publish(self, message: Dict[str, Any]) -> bool:
        """Persist a message to history and broadcast it via pub/sub.

        The sender's own copy also arrives through pub/sub, which keeps
        ordering identical for every subscriber. Returns False when Redis
        rejected the write (the caller should tell the client).
        """
        if self._client is None:
            return False
        raw = json.dumps(message)
        try:
            async with self._client.pipeline(transaction=False) as pipe:
                pipe.lpush(self._history_key, raw)
                pipe.ltrim(self._history_key, 0, self._history_size - 1)
                pipe.publish(self._channel, raw)
                await pipe.execute()
        except RedisError as e:
            logger.warning(f"Chat publish failed: {e}")
            return False
        return True

    async def history(self) -> List[Dict[str, Any]]:
        """Return the stored messages, oldest first. Best-effort."""
        if self._client is None:
            return []
        try:
            raw_items = await self._client.lrange(self._history_key, 0, -1)
        except RedisError as e:
            logger.warning(f"Chat history read failed: {e}")
            return []
        messages = []
        for raw in reversed(raw_items):
            try:
                messages.append(json.loads(raw))
            except (ValueError, TypeError):
                logger.warning("Corrupt chat history entry, skipping")
        return messages

    # -- pub/sub listener ----------------------------------------------------

    async def run_listener(self) -> None:
        """Subscribe to the channel and fan messages out to local sockets.

        Runs for the lifetime of the app (one task per gateway instance) and
        re-subscribes after transient Redis failures.
        """
        while True:
            if self._client is None:
                await asyncio.sleep(_LISTENER_RETRY_DELAY)
                await self.connect()
                continue
            try:
                async with self._client.pubsub() as pubsub:
                    await pubsub.subscribe(self._channel)
                    async for item in pubsub.listen():
                        if item["type"] == "message":
                            await self._broadcast(item["data"])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # The listener must never die silently: a dead listener means a
                # chat that accepts messages but stops delivering them.
                logger.warning(f"Chat listener dropped, retrying: {e}")
                await asyncio.sleep(_LISTENER_RETRY_DELAY)

    async def _broadcast(self, raw: str) -> None:
        """Send a raw JSON payload to every local connection, pruning dead ones."""
        dead = []
        # Snapshot: connections may (un)register while we await inside the loop.
        for websocket in list(self._connections):
            try:
                await websocket.send_text(raw)
            except Exception:
                # The receive loop owns proper cleanup; just stop sending here.
                dead.append(websocket)
        for websocket in dead:
            self._connections.discard(websocket)
