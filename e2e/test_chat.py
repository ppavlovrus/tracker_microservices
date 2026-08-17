"""E2E test for the WebSocket chat.

Needs the ``websockets`` package (pip install websockets) and a running
compose stack. For the heartbeat check, start the gateway with short knobs:

    CHAT_HEARTBEAT_INTERVAL=1 CHAT_HEARTBEAT_TIMEOUT=3 docker compose up -d gateway

Usage: python3 e2e/test_chat.py
"""

import asyncio
import json
import sys
import urllib.request

import websockets

BASE = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/chat"


def login(username: str = "admin", password: str = "admin") -> str:
    """Log in over HTTP and return the session cookie header value."""
    req = urllib.request.Request(
        f"{BASE}/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        set_cookie = resp.headers.get("Set-Cookie", "")
    cookie = set_cookie.split(";")[0]
    assert cookie.startswith("session="), f"no session cookie: {set_cookie}"
    return cookie


async def recv_frame(ws, want_type: str, timeout: float = 5.0) -> dict:
    """Receive frames until one of ``want_type`` arrives (answers pings)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
        if frame["type"] == "ping":
            await ws.send(json.dumps({"type": "pong"}))
        if frame["type"] == want_type:
            return frame


async def main() -> None:
    cookie = login()
    headers = {"Cookie": cookie}
    ok = lambda name: print(f"ok: {name}")

    # 1. Unauthenticated connection is closed with 4401
    async with websockets.connect(WS_URL) as ws:
        closed = False
        try:
            await asyncio.wait_for(ws.recv(), timeout=5)
        except websockets.ConnectionClosed as e:
            assert e.rcvd.code == 4401, f"expected 4401, got {e.rcvd.code}"
            closed = True
        assert closed, "unauthenticated socket was not closed"
    ok("unauthenticated connect rejected with 4401")

    # 2. Two clients: both get history on connect, message reaches both
    async with (
        websockets.connect(WS_URL, additional_headers=headers) as a,
        websockets.connect(WS_URL, additional_headers=headers) as b,
    ):
        hist_a = await recv_frame(a, "history")
        hist_b = await recv_frame(b, "history")
        assert isinstance(hist_a["messages"], list)
        ok("history frame delivered on connect")

        marker = f"e2e chat message {id(a)}"
        await a.send(json.dumps({"type": "message", "text": marker}))
        msg_a = await recv_frame(a, "message")
        msg_b = await recv_frame(b, "message")
        assert msg_a["text"] == marker and msg_b["text"] == marker
        assert msg_a["username"] == "admin"
        assert msg_a["id"] == msg_b["id"], "clients saw different message ids"
        ok("message fanned out to both clients (sender included)")

    # 3. New client sees the message in history (Redis LIST persistence)
    async with websockets.connect(WS_URL, additional_headers=headers) as c:
        hist = await recv_frame(c, "history")
        texts = [m["text"] for m in hist["messages"]]
        assert marker in texts, f"history misses the message: {texts[-3:]}"
        ok("new client receives the message via history replay")

    # 4. Heartbeat: server pings a silent client; without pongs it closes
    #    the connection (requires short CHAT_HEARTBEAT_* on the gateway)
    async with websockets.connect(WS_URL, additional_headers=headers) as d:
        await recv_frame(d, "history")
        got_ping = False
        try:
            while True:
                frame = json.loads(await asyncio.wait_for(d.recv(), timeout=10))
                if frame["type"] == "ping":
                    got_ping = True  # deliberately never answer
        except websockets.ConnectionClosed as e:
            assert got_ping, "connection closed before any ping was seen"
            assert e.rcvd.code == 1001, f"expected 1001, got {e.rcvd.code}"
        except TimeoutError:
            raise AssertionError("silent client was never disconnected")
    ok("silent client is pinged, then dropped on heartbeat timeout")

    # 5. A client that answers pings stays connected past the timeout
    async with websockets.connect(WS_URL, additional_headers=headers) as e:
        await recv_frame(e, "history")
        for _ in range(2):
            await recv_frame(e, "ping", timeout=10)  # recv_frame answers it
        await e.send(json.dumps({"type": "message", "text": "still alive"}))
        msg = await recv_frame(e, "message")
        assert msg["text"] == "still alive"
        ok("client answering pings survives past the heartbeat timeout")

    print("ALL PASSED")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as err:
        print(f"FAIL: {err}", file=sys.stderr)
        sys.exit(1)
