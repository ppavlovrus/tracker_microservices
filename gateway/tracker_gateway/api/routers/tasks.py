"""Tasks router for Gateway API.

Every endpoint here does the same three things and nothing else: turn the
request into a bus contract, hand it to the service, and shape the answer for
HTTP. No try/except on the task paths, no cache, no events -- those moved to
``service/tasks.py``, which has no idea HTTP exists.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from task_tracker_common.contracts.base import INT4_MAX
from task_tracker_common.contracts.commands import TagCreationContract, TaskCreationContract, TaskUpdatePayloadContract

from ...core.exceptions import TagNotFoundError
from ..deps import TagsServiceDep, TasksServiceDep
from ..schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskStatsResponse,
    TaskTag,
    TaskTagAdd,
    TaskUpdate,
)

# Path ids are bounded to the width of the column they address. The bound is not
# decoration: the payload contracts require a positive int4, and a contract that
# fails to build inside the bus client would surface as a bare 500. The edge
# must be at least as strict as the contract behind it.
TaskId = Annotated[int, Path(ge=1, le=INT4_MAX)]
TagId = Annotated[int, Path(ge=1, le=INT4_MAX)]

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate, service: TasksServiceDep) -> TaskResponse:
    """Create a new task."""
    created = await service.create(TaskCreationContract(**task.model_dump()))
    return TaskResponse(**created.model_dump())


@router.get("/stats", response_model=TaskStatsResponse)
async def task_stats(service: TasksServiceDep) -> TaskStatsResponse:
    """Return task counts per status for the Kanban column totals.

    Declared before ``/{task_id}`` so "stats" is not parsed as a task id.
    """
    counts = await service.stats()

    # The worker answers {"total": n, "1": n, ...}: split the total out and
    # coerce the per-status keys to ints for the typed response.
    by_status = {int(key): value for key, value in counts.items() if key != "total"}
    return TaskStatsResponse(total=counts["total"], by_status=by_status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: TaskId, service: TasksServiceDep) -> TaskResponse:
    """Get task by ID."""
    task = await service.get(task_id)
    return TaskResponse(**task.model_dump())


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    service: TasksServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListResponse:
    """List tasks with pagination."""
    page = await service.list_tasks(limit=limit, offset=offset)

    # `limit` and `offset` are the caller's own request echoed back; the page
    # itself does not carry them, because the bus contract describes the data.
    return TaskListResponse(
        tasks=[TaskResponse(**task.model_dump()) for task in page.tasks],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: TaskId, task: TaskUpdate, service: TasksServiceDep) -> TaskResponse:
    """Update task by ID."""
    # exclude_unset survives the trip: only the fields the caller named end up
    # set on the contract, and only those are sent on.
    update = TaskUpdatePayloadContract(**task.model_dump(exclude_unset=True))
    updated = await service.update(task_id, update)
    return TaskResponse(**updated.model_dump())


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: TaskId, service: TasksServiceDep) -> None:
    """Delete task by ID."""
    await service.delete(task_id)


@router.post("/{task_id}/tags", response_model=list[TaskTag])
async def add_task_tag(
    task_id: TaskId, payload: TaskTagAdd, service: TasksServiceDep, tags: TagsServiceDep
) -> list[TaskTag]:
    """Attach a tag (by name, created on demand) to a task."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name must not be blank")

    try:
        tag = await tags.get_by_name(name)
    except TagNotFoundError:
        # Creating the tag is a write to a second service, and this endpoint
        # has no way to undo it. Do not make that write until the task is known
        # to exist, or tagging a task that is gone leaves behind a tag nothing
        # points at. The check is a cache-aside read, so it is usually free.
        #
        # It narrows the window rather than closing it: a task deleted between
        # this read and the link below still orphans one tag row. Closing it
        # properly needs the two writes behind one command, which is work for
        # the tags vertical.
        await service.get(task_id)
        tag = await tags.create(TagCreationContract(name=name))

    # A missing task arrives as TaskNotFoundError and becomes a 404 in one
    # place. This used to be decided by searching the worker's error text for
    # the words "not found".
    linked = await service.add_tag(task_id, tag.id)
    return [TaskTag(**tag.model_dump()) for tag in linked]


@router.delete("/{task_id}/tags/{tag_id}", response_model=list[TaskTag])
async def remove_task_tag(task_id: TaskId, tag_id: TagId, service: TasksServiceDep) -> list[TaskTag]:
    """Detach a tag from a task."""
    tags = await service.remove_tag(task_id, tag_id)
    return [TaskTag(**tag.model_dump()) for tag in tags]
