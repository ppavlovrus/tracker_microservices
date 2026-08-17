"""E2E test for SSE task notifications (/sse/tasks).

Needs a running compose stack. Uses only the standard library.

    python3 e2e/test_sse.py

Cross-instance delivery (events published on one gateway reaching a client
connected to another) is checked when a second gateway is available; point at
it with SSE_SECOND_GATEWAY, e.g.:

    SSE_SECOND_GATEWAY=http://localhost:8001 python3 e2e/test_sse.py
"""

import json
import os
import queue
import sys
import threading
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
SECOND = os.getenv("SSE_SECOND_GATEWAY")  # optional cross-instance target


def login(base: str = BASE) -> str:
    """Log in over HTTP and return the session cookie header value."""
    req = urllib.request.Request(
        f"{base}/auth/login",
        data=json.dumps({"username": "admin", "password": "admin"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        cookie = resp.headers.get("Set-Cookie", "").split(";")[0]
    assert cookie.startswith("session="), f"no session cookie: {cookie}"
    return cookie


class SSEListener(threading.Thread):
    """Read an SSE stream in the background, pushing events onto a queue."""

    def __init__(self, base: str, cookie: str):
        super().__init__(daemon=True)
        self._base = base
        self._cookie = cookie
        self.events: queue.Queue[dict] = queue.Queue()
        self._stop = threading.Event()
        self.ready = threading.Event()

    def run(self) -> None:
        req = urllib.request.Request(f"{self._base}/sse/tasks", headers={"Cookie": self._cookie})
        resp = urllib.request.urlopen(req)
        ctype = resp.headers.get("Content-Type", "")
        assert ctype.startswith("text/event-stream"), f"bad content-type: {ctype}"
        self.ready.set()

        event_type = None
        for raw in resp:  # iterates line by line
            if self._stop.is_set():
                break
            line = raw.decode().rstrip("\n")
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
            elif line.startswith("data:"):
                payload = json.loads(line[len("data:") :].strip())
                self.events.put({"type": event_type, "data": payload})
            elif line == "":
                event_type = None  # end of one event block

    def wait_for(self, event_type: str, predicate=None, timeout: float = 8.0) -> dict:
        """Return the next queued event of ``event_type`` matching ``predicate``."""
        import time

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"timed out waiting for {event_type}")
            try:
                ev = self.events.get(timeout=remaining)
            except queue.Empty:
                raise AssertionError(f"timed out waiting for {event_type}")
            if ev["type"] == event_type and (predicate is None or predicate(ev)):
                return ev

    def stop(self) -> None:
        self._stop.set()


def create_task(cookie: str, title: str) -> int:
    req = urllib.request.Request(
        f"{BASE}/tasks",
        data=json.dumps({"title": title, "creator_id": 1}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["id"]


def update_task(cookie: str, task_id: int, title: str) -> None:
    req = urllib.request.Request(
        f"{BASE}/tasks/{task_id}",
        data=json.dumps({"title": title}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie},
        method="PUT",
    )
    urllib.request.urlopen(req).read()


def delete_task(cookie: str, task_id: int) -> None:
    req = urllib.request.Request(
        f"{BASE}/tasks/{task_id}",
        headers={"Cookie": cookie},
        method="DELETE",
    )
    urllib.request.urlopen(req).read()


def main() -> None:
    ok = lambda name: print(f"ok: {name}")
    cookie = login()

    # 1. Unauthenticated stream is refused with 401
    try:
        urllib.request.urlopen(urllib.request.Request(f"{BASE}/sse/tasks"))
        raise AssertionError("unauthenticated SSE stream was not refused")
    except urllib.error.HTTPError as e:
        assert e.code == 401, f"expected 401, got {e.code}"
    ok("unauthenticated stream rejected with 401")

    # 2. Connect, then create/update/delete and observe the events live
    listener = SSEListener(BASE, cookie)
    listener.start()
    assert listener.ready.wait(timeout=5), "SSE stream did not open"
    ok("authenticated stream opened (text/event-stream)")

    marker = f"e2e sse task {os.getpid()}"
    task_id = create_task(cookie, marker)
    ev = listener.wait_for("task.created", lambda e: e["data"].get("task", {}).get("id") == task_id)
    assert ev["data"]["task"]["title"] == marker
    ok("task.created delivered with the task payload")

    update_task(cookie, task_id, marker + " (upd)")
    ev = listener.wait_for("task.updated", lambda e: e["data"].get("task", {}).get("id") == task_id)
    assert ev["data"]["task"]["title"] == marker + " (upd)"
    ok("task.updated delivered with the updated payload")

    delete_task(cookie, task_id)
    listener.wait_for("task.deleted", lambda e: e["data"].get("id") == task_id)
    ok("task.deleted delivered")

    listener.stop()

    # 3. Cross-instance: a client on the second gateway sees events published
    #    by a write on the first (Redis pub/sub fan-out), if one is available.
    if SECOND:
        cookie2 = login(SECOND)
        other = SSEListener(SECOND, cookie2)
        other.start()
        assert other.ready.wait(timeout=5), "second SSE stream did not open"
        cross_marker = f"e2e sse cross {os.getpid()}"
        cross_id = create_task(cookie, cross_marker)
        other.wait_for("task.created", lambda e: e["data"].get("task", {}).get("id") == cross_id)
        delete_task(cookie, cross_id)
        other.stop()
        ok("event published on gateway A reached a client on gateway B")

    print("ALL PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as err:
        print(f"FAIL: {err}", file=sys.stderr)
        sys.exit(1)
