"""Characterization of the tasks HTTP API as it behaves today.

Expectations here were recorded from a live run, not designed. If one of them
turns red during the refactor, the refactor changed behaviour -- decide whether
that was intended before touching the assertion.
"""

from contracts import StatsContract, TaskContract, TaskListContract


async def test_create_task_returns_201_with_the_full_task(auth_client, trash):
    # Arrange
    payload = {"title": "characterization probe", "creator_id": 1}

    # Act
    response = await auth_client.post("/tasks", json=payload)

    # Assert
    assert response.status_code == 201
    task = TaskContract.model_validate(response.json())
    trash.append(task.id)
    assert task.title == "characterization probe"
    assert task.creator_id == 1


async def test_create_task_without_session_returns_401(client):
    payload = {"title": "characterization no session task create", "creator_id": 1}
    response = await client.post("/tasks", json=payload)
    assert response.status_code == 401


async def test_get_missing_task_returns_404(auth_client, make_task):
    payload = {"creator_id": 1}
    task = await make_task(**payload)
    deleted = await auth_client.delete(f"/tasks/{task.id}")
    assert deleted.status_code == 204

    response = await auth_client.get(f"/tasks/{task.id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_broken_body_422(auth_client):
    payload = {"creator_id": 1}
    response = await auth_client.post("/tasks", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any("title" in item["loc"] for item in detail)


async def test_broken_body_401(client):
    payload = {"creator_id": 1}
    response = await client.post("/tasks", json=payload)
    assert response.status_code == 401


async def test_task_create_increase_total_and_status_counter_by_1(auth_client, make_task):
    response = await auth_client.get("/tasks/stats")
    assert response.status_code == 200
    before = StatsContract.model_validate(response.json())
    payload = {"status_id": 1}
    await make_task(**payload)
    response2 = await auth_client.get("/tasks/stats")
    assert response2.status_code == 200
    after = StatsContract.model_validate(response2.json())
    assert after.total - before.total == 1
    # "1" may be absent from the "before" snapshot on a database with no tasks
    # in that status yet; after creating one it must be there.
    assert after.by_status["1"] - before.by_status.get("1", 0) == 1
    assert sum(after.by_status.values()) == after.total


async def test_get_limits_5_and_offset_0(auth_client):
    response = await auth_client.get("/tasks", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    body = TaskListContract.model_validate(response.json())
    assert body.limit == 5
    assert body.offset == 0
    assert len(body.tasks) <= 5
    assert body.total >= len(body.tasks)


async def test_pages_do_not_overlap(auth_client, make_task):
    await make_task()
    await make_task()
    response1 = await auth_client.get("/tasks", params={"limit": 1, "offset": 0})
    assert response1.status_code == 200
    body1 = TaskListContract.model_validate(response1.json())
    response2 = await auth_client.get("/tasks", params={"limit": 1, "offset": 1})
    assert response2.status_code == 200
    body2 = TaskListContract.model_validate(response2.json())
    ids_first = {task.id for task in body1.tasks}
    ids_second = {task.id for task in body2.tasks}
    assert len(body1.tasks) == 1
    assert len(body2.tasks) == 1
    assert ids_first.isdisjoint(ids_second)


async def test_update_invalidates_cached_task(auth_client, make_task):
    task = await make_task()
    test_string = "this is super-puper-title"
    # Warm the cache: without this read the GET below would go to the worker
    # anyway and the test would pass even with invalidation removed.
    # Verified by mutation -- commenting out cache.delete in update_task (routers/tasks.py)
    # turns this test red and nothing else.
    response = await auth_client.get(f"/tasks/{task.id}")
    assert response.status_code == 200
    payload = {"title": test_string}
    response2 = await auth_client.put(f"/tasks/{task.id}", json=payload)
    assert response2.status_code == 200
    response3 = await auth_client.get(f"/tasks/{task.id}")
    assert response3.status_code == 200
    task_updated = TaskContract.model_validate(response3.json())
    assert task_updated.title == test_string


async def test_unknown_field_in_request_totally_ignored(auth_client, trash):
    payload = {"title": "supertest", "creator_id": 1, "totally_unknown_field": 42}
    response = await auth_client.post("/tasks", json=payload)
    assert response.status_code == 201
    task = TaskContract.model_validate(response.json())
    trash.append(task.id)
    assert task.title == "supertest"
    assert task.creator_id == 1
