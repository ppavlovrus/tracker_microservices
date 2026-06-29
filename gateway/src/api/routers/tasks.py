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
)

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

    # Cache-aside: try the cache first. The list uses a short TTL and is not
    # explicitly invalidated -- a single write can land on any page, so we let
    # the page self-expire rather than track which keys went stale.
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

        # Invalidate the cached task so the next GET re-fetches fresh data
        if cache:
            await cache.delete(_task_key(task_id))

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

        # Invalidate the cached task
        if cache:
            await cache.delete(_task_key(task_id))

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
