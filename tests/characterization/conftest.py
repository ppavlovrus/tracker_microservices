import os

import httpx
import pytest
from contracts import TaskContract

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        yield client


@pytest.fixture
async def auth_client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        response = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200, f"Login failed: {response.status_code} {response.text}"
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
async def trash(auth_client):
    """Ids to delete no matter how the test ends."""
    ids = []
    yield ids
    for task_id in ids:
        await auth_client.delete(f"/tasks/{task_id}")
