"""Characterization of the comments HTTP API as it behaves today.

Expectations here were recorded from a live run, not designed. If one of them
turns red during the refactor, the refactor changed behaviour -- decide whether
that was intended before touching the assertion.
"""

import pytest
from contracts import CommentContract, CommentListContract


async def test_create_comment_returns_201_with_the_full_comment(auth_client, make_comment):
    comment, task = await make_comment()

    assert comment.task_id == task.id
    assert comment.user_id == 1
    assert comment.content == "characterization probe"


async def test_create_comment_without_session_returns_401(client):
    payload = {"task_id": 1, "user_id": 1, "content": "no session probe"}
    response = await client.post("/comments", json=payload)
    assert response.status_code == 401


async def test_create_comment_on_a_missing_task_returns_404(auth_client):
    payload = {"task_id": 999999, "user_id": 1, "content": "ghost task probe"}

    response = await auth_client.post("/comments", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


async def test_create_comment_from_a_missing_user_returns_404(auth_client, make_task):
    task = await make_task()
    payload = {"task_id": task.id, "user_id": 999999, "content": "ghost user probe"}

    response = await auth_client.post("/comments", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


async def test_get_missing_comment_returns_404(auth_client):
    response = await auth_client.get("/comments/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Comment not found"


@pytest.mark.parametrize("bad_id", [0, -1, 3_000_000_000])
async def test_comment_paths_refuse_an_id_the_column_cannot_hold(auth_client, bad_id):
    # Before the contracts refactor: 0 and negatives answered 404 "Comment
    # not found", anything past int4 a 500 from the driver. The bus contract
    # first refused them (400 through the raw router); the thin router now
    # holds the same line at its own edge and answers 422 before the bus.
    response = await auth_client.get(f"/comments/{bad_id}")
    assert response.status_code == 422


@pytest.mark.parametrize("bad_task_id", [0, -1, 3_000_000_000])
async def test_comment_list_refuses_a_task_id_the_column_cannot_hold(auth_client, bad_task_id):
    # Same history as the path ids, one level over: 0 answered 400 "Task ID
    # is required", negatives an empty 200 (no task can have that id), and
    # anything past int4 a 500 from the driver.
    response = await auth_client.get("/comments", params={"task_id": bad_task_id})
    assert response.status_code == 422


async def test_broken_body_422(auth_client):
    payload = {"task_id": 1, "user_id": 1}
    response = await auth_client.post("/comments", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any("content" in item["loc"] for item in detail)


async def test_list_comments_counts_only_the_asked_task(auth_client, make_task, make_comment):
    task = await make_task()
    first, _ = await make_comment(task=task)
    second, _ = await make_comment(task=task, content="second probe")
    # A comment on another task must not leak into this task's total.
    elsewhere, _ = await make_comment()

    response = await auth_client.get("/comments", params={"task_id": task.id})

    assert response.status_code == 200
    body = CommentListContract.model_validate(response.json())
    assert body.total == 2
    assert {c.id for c in body.comments} == {first.id, second.id}
    assert all(c.task_id == task.id for c in body.comments)
    assert elsewhere.id not in {c.id for c in body.comments}


async def test_list_comments_requires_the_task_query_param(auth_client):
    response = await auth_client.get("/comments")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any("task_id" in item["loc"] for item in detail)


async def test_update_comment_changes_content_and_touches_updated_at(auth_client, make_comment):
    comment, _ = await make_comment()

    response = await auth_client.put(f"/comments/{comment.id}", json={"content": "edited probe"})

    assert response.status_code == 200
    edited = CommentContract.model_validate(response.json())
    assert edited.content == "edited probe"
    assert edited.created_at == comment.created_at
    assert edited.updated_at != comment.updated_at

    # And the edit was stored, not echoed.
    reread = await auth_client.get(f"/comments/{comment.id}")
    assert CommentContract.model_validate(reread.json()).content == "edited probe"


async def test_update_missing_comment_returns_404(auth_client):
    response = await auth_client.put("/comments/999999", json={"content": "ghost"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Comment not found"


async def test_delete_comment_answers_204_and_then_it_is_gone(auth_client, make_comment):
    comment, _ = await make_comment()

    deleted = await auth_client.delete(f"/comments/{comment.id}")

    assert deleted.status_code == 204
    gone = await auth_client.get(f"/comments/{comment.id}")
    assert gone.status_code == 404


async def test_delete_missing_comment_returns_404(auth_client):
    response = await auth_client.delete("/comments/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Comment not found"
