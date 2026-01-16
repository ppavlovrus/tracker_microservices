"""Tasks router for Gateway API."""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated

from ...config import RPC_TIMEOUT
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


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


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
    
    try:
        # Send RPC command to Tasks service
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
        
        logger.debug(f"Task {task_id} retrieved successfully")
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
        
        logger.debug(f"Listed {len(tasks)} tasks (limit={limit}, offset={offset})")
        return TaskListResponse(
            tasks=tasks,
            total=data.get("total", len(tasks)),
            limit=limit,
            offset=offset
        )
        
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
