"""Tasks router for Gateway API.

The router does three things and no more: turn a request into a command, ask
the bus, and shape the answer for HTTP. It has no try/except and raises no
HTTPException -- failures travel as domain errors and become statuses in
``api/errors.py``. What is left here that is not plumbing is the caching and
the change notifications.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from task_tracker_common.contracts.base import INT4_MAX
from task_tracker_common.contracts.commands import TaskCreationContract, TaskUpdatePayloadContract

from ...broker.tasks_client import TasksBusClient
from ...config import CACHE_TTL_TASK, CACHE_TTL_TASKS_LIST, RPC_TIMEOUT
from ..schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskStatsResponse,
    TaskTag,
    TaskTagAdd,
    TaskUpdate,
)

# Queue of the tags service, used when resolving a tag by name. Still spoken to
# raw: the tags vertical has not moved onto contracts yet.
TAGS_QUEUE = "tags.commands"

# Path ids are bounded to the width of the column they address. The bound is not
# decoration: the payload contracts require a positive int4, and a contract that
# fails to build inside the bus client would surface as a bare 500. The edge
# must be at least as strict as the contract behind it.
TaskId = Annotated[int, Path(ge=1, le=INT4_MAX)]
TagId = Annotated[int, Path(ge=1, le=INT4_MAX)]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# Until the lifespan hands us a live connection this client answers
# BusUnavailableError, which is exactly what is true before startup finishes.
bus = TasksBusClient(None)

# Raw client, kept only for the tags service (see TAGS_QUEUE above).
rabbitmq_client = None

# Global cache instance (will be set in main.py lifespan)
cache = None

# Global events hub for SSE notifications (will be set in main.py lifespan)
events_hub = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global bus, rabbitmq_client
    bus = TasksBusClient(client)
    rabbitmq_client = client


def set_cache(c):
    """Set cache instance."""
    global cache
    cache = c


def set_events_hub(hub):
    """Set events hub instance for SSE task notifications."""
    global events_hub
    events_hub = hub


async def _publish_event(event_type: str, payload: dict) -> None:
    """Best-effort SSE notification about a task change.

    Never raised into the request: a failed notification must not fail the
    write it describes.
    """
    if not events_hub:
        return
    event = {
        "type": event_type,
        "ts": datetime.now(UTC).isoformat(),
        **payload,
    }
    await events_hub.publish(event)


def _task_key(task_id: int) -> str:
    """Cache key for a single task."""
    return f"task:{task_id}"


def _tasks_list_key(limit: int, offset: int) -> str:
    """Cache key for a tasks-list page."""
    return f"tasks:list:{limit}:{offset}"


async def _invalidate_task_cache(task_id: int) -> None:
    """Drop the cached task and all list pages after a write."""
    if cache:
        await cache.delete(_task_key(task_id))
        await cache.delete_pattern("tasks:list:*")


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate) -> TaskResponse:
    """Create a new task."""
    created = await bus.create(TaskCreationContract(**task.model_dump()))

    # A new task can appear on any list page -> drop all cached pages.
    if cache:
        await cache.delete_pattern("tasks:list:*")

    result = TaskResponse(**created.model_dump())
    await _publish_event("task.created", {"task": result.model_dump(mode="json")})

    logger.info(f"Task created successfully: {result.id}")
    return result


@router.get("/stats", response_model=TaskStatsResponse)
async def task_stats() -> TaskStatsResponse:
    """Return task counts per status for the Kanban column totals.

    Declared before ``/{task_id}`` so "stats" is not parsed as a task id. Not
    cached: it is a single-scan aggregate and must reflect writes immediately.
    """
    counts = await bus.stats()

    # The worker answers {"total": n, "1": n, ...}: split the total out and
    # coerce the per-status keys to ints for the typed response.
    by_status = {int(key): value for key, value in counts.items() if key != "total"}
    return TaskStatsResponse(total=counts["total"], by_status=by_status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: TaskId) -> TaskResponse:
    """Get task by ID."""
    # Cache-aside: try the cache first
    if cache:
        cached = await cache.get_json(_task_key(task_id))
        if cached is not None:
            logger.debug(f"Cache HIT for task {task_id}")
            return TaskResponse(**cached)

    result = TaskResponse(**(await bus.get(task_id)).model_dump())

    # Populate the cache for next time
    if cache:
        await cache.set_json(_task_key(task_id), result.model_dump(mode="json"), CACHE_TTL_TASK)

    logger.debug(f"Cache MISS for task {task_id}, served from RPC")
    return result


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    limit: Annotated[int, Query(ge=1, le=100)] = 10, offset: Annotated[int, Query(ge=0)] = 0
) -> TaskListResponse:
    """List tasks with pagination."""
    # Cache-aside with a short TTL. List pages are also invalidated on every
    # task write (create/update/delete drop all `tasks:list:*` keys), so the UI
    # sees changes immediately; the TTL is just a backstop.
    if cache:
        cached = await cache.get_json(_tasks_list_key(limit, offset))
        if cached is not None:
            logger.debug(f"Cache HIT for tasks list (limit={limit}, offset={offset})")
            return TaskListResponse(**cached)

    page = await bus.list_tasks(limit=limit, offset=offset)

    # `total` comes from the contract, which requires it. It used to fall back
    # to the length of the page, which quietly turned the last page into the
    # whole table.
    result = TaskListResponse(
        tasks=[TaskResponse(**task.model_dump()) for task in page.tasks],
        total=page.total,
        limit=limit,
        offset=offset,
    )

    # Populate the cache with a short TTL
    if cache:
        await cache.set_json(_tasks_list_key(limit, offset), result.model_dump(mode="json"), CACHE_TTL_TASKS_LIST)

    logger.debug(f"Listed {len(result.tasks)} tasks (limit={limit}, offset={offset})")
    return result


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: TaskId, task: TaskUpdate) -> TaskResponse:
    """Update task by ID."""
    # exclude_unset survives the trip: only the fields the caller named end up
    # set on the contract, and only those are sent on.
    update = TaskUpdatePayloadContract(**task.model_dump(exclude_unset=True))
    updated = await bus.update(task_id, update)

    await _invalidate_task_cache(task_id)

    result = TaskResponse(**updated.model_dump())
    await _publish_event("task.updated", {"task": result.model_dump(mode="json")})

    logger.info(f"Task {task_id} updated successfully")
    return result


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: TaskId) -> None:
    """Delete task by ID."""
    await bus.delete(task_id)

    await _invalidate_task_cache(task_id)
    await _publish_event("task.deleted", {"id": task_id})

    logger.info(f"Task {task_id} deleted successfully")


async def _resolve_tag_id(name: str) -> int:
    """Return the id of the tag named ``name``, creating it if needed.

    Still raw RPC and still raising HTTPException: this talks to the tags
    service, which has no contracts yet. It moves when that vertical does.
    """
    existing = await rabbitmq_client.call(
        queue_name=TAGS_QUEUE,
        message={"command": "get_tag_by_name", "data": {"name": name}},
        timeout=RPC_TIMEOUT,
    )
    if existing.get("success"):
        return existing["data"]["id"]

    created = await rabbitmq_client.call(
        queue_name=TAGS_QUEUE,
        message={"command": "create_tag", "data": {"name": name}},
        timeout=RPC_TIMEOUT,
    )
    if not created.get("success"):
        raise HTTPException(status_code=400, detail=created.get("error", "Failed to create tag"))
    return created["data"]["id"]


@router.post("/{task_id}/tags", response_model=list[TaskTag])
async def add_task_tag(task_id: TaskId, payload: TaskTagAdd) -> list[TaskTag]:
    """Attach a tag (by name, created on demand) to a task."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name must not be blank")

    tag_id = await _resolve_tag_id(name)

    # A missing task now arrives as TaskNotFoundError and becomes a 404 in one
    # place. This used to be decided by searching the worker's error text for
    # the words "not found".
    tags = await bus.add_tag(task_id, tag_id)

    await _invalidate_task_cache(task_id)
    await _publish_event("task.updated", {"id": task_id})
    return [TaskTag(**tag.model_dump()) for tag in tags.tags]


@router.delete("/{task_id}/tags/{tag_id}", response_model=list[TaskTag])
async def remove_task_tag(task_id: TaskId, tag_id: TagId) -> list[TaskTag]:
    """Detach a tag from a task."""
    tags = await bus.remove_tag(task_id, tag_id)

    await _invalidate_task_cache(task_id)
    await _publish_event("task.updated", {"id": task_id})
    return [TaskTag(**tag.model_dump()) for tag in tags.tags]
