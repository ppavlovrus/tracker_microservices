import os
from uuid import uuid4

import httpx
import pytest
from contracts import AttachmentInitiateContract, CommentContract, TagContract, TaskContract, UserContract

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# httpx reads proxy settings from the environment. These tests talk to localhost
# and must not go through the cascade SOCKS proxy -- with it enabled the whole run
# dies at import time with "ImportError: socksio". Hence trust_env=False below.

# The admin session, logged in once per run: (cookie name, cookie value).
# The gateway rate-limits by IP (a 60-token bucket refilling at 10/s) and a
# suite that logs in per test spends its whole budget on logins; the session
# outlives the run by hours.
_admin_session_cookie: tuple[str, str] | None = None


@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, trust_env=False) as client:
        yield client


@pytest.fixture
async def auth_client():
    global _admin_session_cookie
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, trust_env=False) as client:
        if _admin_session_cookie is None:
            response = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
            assert response.status_code == 200, f"Login failed: {response.status_code} {response.text}"
            # One cookie comes back; take its name from the answer instead of
            # hardcoding the gateway's choice here.
            session_cookie = next(iter(response.cookies.jar))
            _admin_session_cookie = (session_cookie.name, session_cookie.value)
        client.cookies.set(*_admin_session_cookie)
        yield client


@pytest.fixture
async def make_task(auth_client):
    """Create tasks and delete every one of them when the test ends."""
    created_ids = []

    async def _make(**overrides) -> TaskContract:
        payload = {"title": "characterization probe", "creator_id": 1} | overrides
        response = await auth_client.post("/tasks", json=payload)
        assert response.status_code == 201, f"setup failed: {response.text}"
        task = TaskContract.model_validate(response.json())
        created_ids.append(task.id)
        return task

    yield _make

    for task_id in created_ids:
        await auth_client.delete(f"/tasks/{task_id}")


@pytest.fixture
async def make_user(auth_client):
    """Create users with unique credentials and delete every one of them after.

    Returns ``(user, payload)``: the payload keeps the plaintext password so a
    test can log in as the user it just created. Credentials are randomised
    because username and email are unique columns -- a fixed name would make
    the second run of a failed test collide with the leftovers of the first.
    """
    created_ids = []

    async def _make(**overrides):
        suffix = uuid4().hex[:10]
        payload = {
            "username": f"probe_{suffix}",
            "email": f"probe_{suffix}@example.com",
            "password": "probe-pass-123",
        } | overrides
        response = await auth_client.post("/users", json=payload)
        assert response.status_code == 201, f"setup failed: {response.text}"
        user = UserContract.model_validate(response.json())
        created_ids.append(user.id)
        return user, payload

    yield _make

    for user_id in created_ids:
        await auth_client.delete(f"/users/{user_id}")


@pytest.fixture
async def make_tag(auth_client):
    """Create tags and delete every one of them when the test ends.

    The name is randomised: ``name`` is a unique column, and a fixed name
    would make the second run of a failed test collide with the leftovers
    of the first.
    """
    created_ids = []

    async def _make(**overrides) -> TagContract:
        payload = {"name": f"tag_probe_{uuid4().hex[:10]}"} | overrides
        response = await auth_client.post("/tags", json=payload)
        assert response.status_code == 201, f"setup failed: {response.text}"
        tag = TagContract.model_validate(response.json())
        created_ids.append(tag.id)
        return tag

    yield _make

    for tag_id in created_ids:
        await auth_client.delete(f"/tags/{tag_id}")


@pytest.fixture
async def tag_trash(auth_client):
    """Tag ids to delete no matter how the test ends.

    For tags the test did not create through ``make_tag`` -- the on-demand
    tag that POST /tasks/{id}/tags leaves behind, for example.
    """
    ids = []
    yield ids
    for tag_id in ids:
        await auth_client.delete(f"/tags/{tag_id}")


@pytest.fixture
async def make_comment(auth_client, make_task):
    """Create a comment (on its own task by default) and clean both up.

    Returns ``(comment, task)``: several tests need the task to ask for the
    comment list. A test that wants several comments on one task passes that
    task in; ``make_task`` still owns its teardown either way.
    """
    comment_ids = []

    async def _make(task=None, **overrides):
        own_task = task if task is not None else await make_task()
        payload = {"task_id": own_task.id, "user_id": 1, "content": "characterization probe"} | overrides
        response = await auth_client.post("/comments", json=payload)
        assert response.status_code == 201, f"setup failed: {response.text}"
        comment = CommentContract.model_validate(response.json())
        comment_ids.append(comment.id)
        return comment, own_task

    yield _make

    for comment_id in comment_ids:
        await auth_client.delete(f"/comments/{comment_id}")


@pytest.fixture
async def make_attachment(auth_client, make_task):
    """Initiate an attachment (metadata + presigned URL, no bytes uploaded).

    Returns ``(attachment, task)``. The S3 object is never uploaded, and the
    teardown delete is fine with that: object-store deletes are idempotent
    for keys that were never written.
    """
    attachment_ids = []

    async def _make(task=None, **overrides):
        own_task = task if task is not None else await make_task()
        payload = {
            "task_id": own_task.id,
            "filename": "probe.txt",
            "content_type": "text/plain",
            "size_bytes": 42,
        } | overrides
        response = await auth_client.post("/attachments", json=payload)
        assert response.status_code == 201, f"setup failed: {response.text}"
        # The create answer is the initiate shape: metadata plus the
        # presigned upload URL. It is a subclass, so a test that only wants
        # the metadata still sees an attachment.
        attachment = AttachmentInitiateContract.model_validate(response.json())
        attachment_ids.append(attachment.id)
        return attachment, own_task

    yield _make

    for attachment_id in attachment_ids:
        await auth_client.delete(f"/attachments/{attachment_id}")


@pytest.fixture
async def trash(auth_client):
    """Ids to delete no matter how the test ends."""
    ids = []
    yield ids
    for task_id in ids:
        await auth_client.delete(f"/tasks/{task_id}")
