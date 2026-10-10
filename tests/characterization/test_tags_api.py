"""Characterization of the tags HTTP API as it behaves today.

Expectations here were recorded from a live run, not designed. If one of
them turns red during the refactor, the refactor changed behaviour -- decide
whether that was intended before touching the assertion.
"""

from uuid import uuid4

import pytest
from contracts import TagContract, TagListContract


async def test_create_tag_returns_201_with_id_and_name(auth_client, tag_trash):
    # A uuid in the name: a leftover from a failed earlier run must not turn
    # this into a duplicate-name answer.
    name = f"probe {uuid4().hex[:8]}"

    response = await auth_client.post("/tags", json={"name": name})

    assert response.status_code == 201
    tag = TagContract.model_validate(response.json())
    tag_trash.append(tag.id)
    assert tag.name == name


async def test_create_tag_without_session_returns_401(client):
    response = await client.post("/tags", json={"name": "no session probe"})
    assert response.status_code == 401


async def test_create_tag_with_a_duplicate_name_returns_409(auth_client, make_tag):
    # Recorded from the live API before the worker moved onto contracts, this
    # answered 400 with free text and no code. The contracts refactor makes
    # the database the only judge of uniqueness and classifies the collision
    # as CONFLICT -- the same 409 a taken username or email gets.
    tag = await make_tag()

    response = await auth_client.post("/tags", json={"name": tag.name})

    assert response.status_code == 409
    assert response.json()["detail"] == "Tag with this name already exists"


async def test_renaming_to_a_taken_name_returns_409(auth_client, make_tag):
    first = await make_tag()
    second = await make_tag()

    response = await auth_client.put(f"/tags/{second.id}", json={"name": first.name})

    assert response.status_code == 409
    assert response.json()["detail"] == "Tag with this name already exists"


async def test_get_created_tag_returns_it(auth_client, make_tag):
    tag = await make_tag()

    response = await auth_client.get(f"/tags/{tag.id}")

    assert response.status_code == 200
    assert TagContract.model_validate(response.json()) == tag


async def test_get_missing_tag_returns_404(auth_client):
    response = await auth_client.get("/tags/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Tag not found"


async def test_create_tag_with_an_empty_name_returns_422(auth_client):
    response = await auth_client.post("/tags", json={"name": ""})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any("name" in item["loc"] for item in detail)


async def test_list_tags_envelope_and_echoes_pagination(auth_client):
    response = await auth_client.get("/tags", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    body = TagListContract.model_validate(response.json())
    assert body.limit == 5
    assert body.offset == 0
    assert len(body.tags) <= 5
    assert body.total >= len(body.tags)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_list_tags_rejects_out_of_bounds_params(auth_client, params):
    response = await auth_client.get("/tags", params=params)
    assert response.status_code == 422


async def test_list_pages_do_not_overlap(auth_client, make_tag):
    await make_tag()
    await make_tag()

    first = await auth_client.get("/tags", params={"limit": 1, "offset": 0})
    second = await auth_client.get("/tags", params={"limit": 1, "offset": 1})

    body1 = TagListContract.model_validate(first.json())
    body2 = TagListContract.model_validate(second.json())
    assert len(body1.tags) == 1
    assert len(body2.tags) == 1
    assert body1.tags[0].id != body2.tags[0].id


async def test_a_tag_created_after_a_warm_list_read_shows_up_in_the_next_read(auth_client, make_tag):
    # List pages are cached in Redis; a write must drop them, or the second
    # read below would happily serve the warmed page without the new tag.
    warm = await auth_client.get("/tags", params={"limit": 100, "offset": 0})
    assert warm.status_code == 200

    tag = await make_tag()

    reread = await auth_client.get("/tags", params={"limit": 100, "offset": 0})
    assert reread.status_code == 200
    body = TagListContract.model_validate(reread.json())
    assert tag.id in {t.id for t in body.tags}


async def test_an_on_demand_tag_invalidates_a_warm_list_read_too(auth_client, make_task, tag_trash):
    # The second entry point that writes tags is POST /tasks/{id}/tags. It
    # used to create tags with raw RPC, which skipped the cache drop; going
    # through the tags service is what makes a warm list page see the tag.
    warm = await auth_client.get("/tags", params={"limit": 100, "offset": 0})
    assert warm.status_code == 200

    task = await make_task()
    name = f"via tasks {uuid4().hex[:8]}"
    attached = await auth_client.post(f"/tasks/{task.id}/tags", json={"name": name})
    assert attached.status_code == 200
    tag_trash.append(attached.json()[0]["id"])

    reread = await auth_client.get("/tags", params={"limit": 100, "offset": 0})
    assert reread.status_code == 200
    body = TagListContract.model_validate(reread.json())
    assert name in {t.name for t in body.tags}


async def test_update_tag_renames_it(auth_client, make_tag):
    tag = await make_tag()
    new_name = f"renamed {uuid4().hex[:8]}"

    response = await auth_client.put(f"/tags/{tag.id}", json={"name": new_name})

    assert response.status_code == 200
    assert TagContract.model_validate(response.json()) == TagContract(id=tag.id, name=new_name)

    # And the rename was stored, not echoed.
    reread = await auth_client.get(f"/tags/{tag.id}")
    assert TagContract.model_validate(reread.json()).name == new_name


async def test_update_missing_tag_returns_404(auth_client):
    response = await auth_client.put("/tags/999999", json={"name": "ghost"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Tag not found"


async def test_delete_tag_answers_204_and_then_the_tag_is_gone(auth_client, make_tag):
    tag = await make_tag()

    deleted = await auth_client.delete(f"/tags/{tag.id}")

    assert deleted.status_code == 204
    gone = await auth_client.get(f"/tags/{tag.id}")
    assert gone.status_code == 404


async def test_delete_missing_tag_returns_404(auth_client):
    response = await auth_client.delete("/tags/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Tag not found"


@pytest.mark.parametrize("bad_id", [0, -1, 3_000_000_000])
async def test_tag_paths_refuse_an_id_the_column_cannot_hold(auth_client, bad_id):
    # Before the contracts refactor these were three different accidents:
    # 0 answered 404 "Tag ID is required", negatives 404 "Tag not found",
    # and anything past int4 a 500 from the driver. The bus contract first
    # refused them (400 through the raw router); the thin router now holds
    # the same line at its own edge and answers 422 before the bus.
    response = await auth_client.get(f"/tags/{bad_id}")
    assert response.status_code == 422


async def test_renaming_a_tag_to_its_own_name_succeeds(auth_client, make_tag):
    # The old handler allowed this explicitly (``existing.id != tag_id``).
    # The constraint allows it too: Postgres excludes the row's own old
    # version from the uniqueness check, so the rename is a no-op that
    # still answers 200.
    tag = await make_tag()

    response = await auth_client.put(f"/tags/{tag.id}", json={"name": tag.name})

    assert response.status_code == 200
    assert TagContract.model_validate(response.json()) == tag


# --- tags through the tasks API ------------------------------------------------
# These pin the flow the tasks router implements: it resolves a tag by name
# and creates it on demand. That flow used to be raw RPC into the tags queue;
# since the tags vertical moved onto contracts it goes through TagService,
# and these tests are what says the port kept the behaviour.


async def test_task_tag_creates_the_tag_on_demand_and_reuses_it(auth_client, make_task, tag_trash):
    task = await make_task()
    name = f"on demand {uuid4().hex[:8]}"

    attached = await auth_client.post(f"/tasks/{task.id}/tags", json={"name": name})

    assert attached.status_code == 200
    tags = [TagContract.model_validate(t) for t in attached.json()]
    assert [t.name for t in tags] == [name]
    tag_trash.append(tags[0].id)

    # The same name again links the same tag instead of colliding on the
    # unique constraint.
    again = await auth_client.post(f"/tasks/{task.id}/tags", json={"name": name})
    assert again.status_code == 200
    assert [t["id"] for t in again.json()] == [tags[0].id]


async def test_task_tag_on_a_missing_task_returns_404_and_leaves_no_tag_behind(auth_client, tag_trash):
    name = f"orphan probe {uuid4().hex[:8]}"

    response = await auth_client.post("/tasks/999999/tags", json={"name": name})

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"

    # The task is checked before the tag is created, so the name was never
    # taken: creating it now must succeed rather than collide.
    created = await auth_client.post("/tags", json={"name": name})
    assert created.status_code == 201
    tag_trash.append(created.json()["id"])


async def test_task_tag_with_a_blank_name_returns_422(auth_client, make_task):
    task = await make_task()

    response = await auth_client.post(f"/tasks/{task.id}/tags", json={"name": "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == "Tag name must not be blank"
