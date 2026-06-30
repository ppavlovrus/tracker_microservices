"""Tasks router for Gateway API."""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated

from ...config import RPC_TIMEOUT, CACHE_TTL_TASK, CACHE_TTL_TASKS_LIST
from ..schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TaskListResponse,
    TaskTag,
    TaskTagAdd,
)

# Queue of the tags service, used when resolving a tag by name.
TAGS_QUEUE = "tags.commands"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None

# Global cache instance (will be set in main.py lifespan)
cache = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


def set_cache(c):
    """Set cache instance."""
    global cache
    cache = c


def _task_key(task_id: int) -> str:
    """Cache key for a single task."""
    return f"task:{task_id}"


def _tasks_list_key(limit: int, offset: int) -> str:
    """Cache key for a tasks-list page."""
    return f"tasks:list:{limit}:{offset}"


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskCreate) -> TaskResponse:
    """
    Create a new task.
    
    Sends command to Tasks microservice via RabbitMQ.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Send RPC command to Tasks service
        response = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "create_task",
                "data": task.model_dump()
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to create task: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        # A new task can appear on any list page -> drop all cached pages.
        if cache:
            await cache.delete_pattern("tasks:list:*")

        logger.info(f"Task created successfully: {response['data'].get('id')}")
        return TaskResponse(**response["data"])
        
    except TimeoutError:
        logger.error("Timeout waiting for Tasks service response")
        raise HTTPException(
            status_code=504,
            detail="Tasks service timeout"
        )
    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int) -> TaskResponse:
    """
    Get task by ID.
    
    Sends command to Tasks microservice via RabbitMQ.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Cache-aside: try the cache first
    if cache:
        cached = await cache.get_json(_task_key(task_id))
        if cached is not None:
            logger.debug(f"Cache HIT for task {task_id}")
            return TaskResponse(**cached)

    try:
        # Cache miss -> send RPC command to Tasks service
        response = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "get_task",
                "data": {"id": task_id}
            },
            timeout=RPC_TIMEOUT
        )

        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "Task not found")
            logger.warning(f"Task {task_id} not found")
            raise HTTPException(status_code=404, detail=error_msg)

        result = TaskResponse(**response["data"])

        # Populate the cache for next time
        if cache:
            await cache.set_json(
                _task_key(task_id), result.model_dump(mode="json"), CACHE_TTL_TASK
            )

        logger.debug(f"Cache MISS for task {task_id}, served from RPC")
        return result
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tasks service response")
        raise HTTPException(
            status_code=504,
            detail="Tasks service timeout"
        )
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0
) -> TaskListResponse:
    """
    List tasks with pagination.
    
    Sends command to Tasks microservice via RabbitMQ.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Cache-aside with a short TTL. List pages are also invalidated on every
    # task write (create/update/delete drop all `tasks:list:*` keys), so the UI
    # sees changes immediately; the TTL is just a backstop.
    if cache:
        cached = await cache.get_json(_tasks_list_key(limit, offset))
        if cached is not None:
            logger.debug(f"Cache HIT for tasks list (limit={limit}, offset={offset})")
            return TaskListResponse(**cached)

    try:
        # Send RPC command to Tasks service
        response = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "list_tasks",
                "data": {
                    "limit": limit,
                    "offset": offset
                }
            },
            timeout=RPC_TIMEOUT
        )

        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to list tasks: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        data = response["data"]
        tasks = [TaskResponse(**task) for task in data["tasks"]]

        result = TaskListResponse(
            tasks=tasks,
            total=data.get("total", len(tasks)),
            limit=limit,
            offset=offset
        )

        # Populate the cache with a short TTL
        if cache:
            await cache.set_json(
                _tasks_list_key(limit, offset),
                result.model_dump(mode="json"),
                CACHE_TTL_TASKS_LIST,
            )

        logger.debug(f"Listed {len(tasks)} tasks (limit={limit}, offset={offset})")
        return result

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tasks service response")
        raise HTTPException(
            status_code=504,
            detail="Tasks service timeout"
        )
    except Exception as e:
        logger.error(f"Error listing tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task: TaskUpdate) -> TaskResponse:
    """
    Update task by ID.
    
    Sends command to Tasks microservice via RabbitMQ.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Send RPC command to Tasks service
        response = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "update_task",
                "data": {
                    "id": task_id,
                    "update": task.model_dump(exclude_unset=True)
                }
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "Task not found")
            logger.warning(f"Failed to update task {task_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        # Invalidate the cached task and all list pages so the next reads are fresh
        if cache:
            await cache.delete(_task_key(task_id))
            await cache.delete_pattern("tasks:list:*")

        logger.info(f"Task {task_id} updated successfully")
        return TaskResponse(**response["data"])
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tasks service response")
        raise HTTPException(
            status_code=504,
            detail="Tasks service timeout"
        )
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int) -> None:
    """
    Delete task by ID.
    
    Sends command to Tasks microservice via RabbitMQ.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Send RPC command to Tasks service
        response = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "delete_task",
                "data": {"id": task_id}
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "Task not found")
            logger.warning(f"Failed to delete task {task_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        # Invalidate the cached task and all list pages
        if cache:
            await cache.delete(_task_key(task_id))
            await cache.delete_pattern("tasks:list:*")

        logger.info(f"Task {task_id} deleted successfully")

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tasks service response")
        raise HTTPException(
            status_code=504,
            detail="Tasks service timeout"
        )
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _resolve_tag_id(name: str) -> int:
    """Return the id of the tag named ``name``, creating it if needed."""
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


async def _invalidate_task_cache(task_id: int) -> None:
    """Drop the cached task and all list pages after a tag change."""
    if cache:
        await cache.delete(_task_key(task_id))
        await cache.delete_pattern("tasks:list:*")


@router.post("/{task_id}/tags", response_model=list[TaskTag])
async def add_task_tag(task_id: int, payload: TaskTagAdd) -> list[TaskTag]:
    """Attach a tag (by name, created on demand) to a task."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name must not be blank")

    try:
        tag_id = await _resolve_tag_id(name)

        link = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "add_task_tag",
                "data": {"task_id": task_id, "tag_id": tag_id},
            },
            timeout=RPC_TIMEOUT,
        )
        if not link.get("success"):
            error_msg = link.get("error", "Failed to add tag")
            status = 404 if "not found" in error_msg.lower() else 400
            raise HTTPException(status_code=status, detail=error_msg)

        await _invalidate_task_cache(task_id)
        return [TaskTag(**t) for t in link["data"]["tags"]]

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for service response")
        raise HTTPException(status_code=504, detail="Service timeout")
    except Exception as e:
        logger.error(f"Error adding tag to task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}/tags/{tag_id}", response_model=list[TaskTag])
async def remove_task_tag(task_id: int, tag_id: int) -> list[TaskTag]:
    """Detach a tag from a task."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        res = await rabbitmq_client.call(
            queue_name="tasks.commands",
            message={
                "command": "remove_task_tag",
                "data": {"task_id": task_id, "tag_id": tag_id},
            },
            timeout=RPC_TIMEOUT,
        )
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Failed to remove tag"))

        await _invalidate_task_cache(task_id)
        return [TaskTag(**t) for t in res["data"]["tags"]]

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tasks service response")
        raise HTTPException(status_code=504, detail="Tasks service timeout")
    except Exception as e:
        logger.error(f"Error removing tag from task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
