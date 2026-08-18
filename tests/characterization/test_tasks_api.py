"""Characterization of the tasks HTTP API as it behaves today.

Expectations here were recorded from a live run, not designed. If one of them
turns red during the refactor, the refactor changed behaviour -- decide whether
that was intended before touching the assertion.
"""

from contracts import TaskContract


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
