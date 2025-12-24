"""Tasks router for Gateway API."""

from fastapi import APIRouter, HTTPException, Depends, status

from gateway.src.messaging import GatewayMessagingClient
from gateway.src.main import get_messaging_client
from gateway.src.api.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TaskListResponse,
    TaskAssignUsers,
    TaskAssignTags,
)

router = APIRouter()


@router.post("/v1/task/create", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """Create a new task.
    
    Args:
        task_data: Task creation data
        client: Gateway messaging client
        
    Returns:
        Created task
        
    Raises:
        HTTPException: If task creation fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        result = await client.create_task(
            task_data=task_data.model_dump(exclude_unset=True),
            user_id=user_id
        )
        return result
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create task: {str(e)}"
        )


@router.get("/v1/task/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """Get a task by ID.
    
    Args:
        task_id: Task ID
        client: Gateway messaging client
        
    Returns:
        Task data
        
    Raises:
        HTTPException: If task not found or retrieval fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        result = await client.get_task(task_id=task_id, user_id=user_id)
        return result
    except RuntimeError as e:
        if "NOT_FOUND" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task: {str(e)}"
        )


@router.put("/v1/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """Update a task.
    
    Args:
        task_id: Task ID
        task_data: Task update data
        client: Gateway messaging client
        
    Returns:
        Updated task
        
    Raises:
        HTTPException: If task not found or update fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        result = await client.update_task(
            task_id=task_id,
            task_data=task_data.model_dump(exclude_unset=True),
            user_id=user_id
        )
        return result
    except RuntimeError as e:
        if "NOT_FOUND" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update task: {str(e)}"
        )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """Delete a task.
    
    Args:
        task_id: Task ID
        client: Gateway messaging client
        
    Raises:
        HTTPException: If task not found or deletion fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        success = await client.delete_task(task_id=task_id, user_id=user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found"
            )
    except RuntimeError as e:
        if "NOT_FOUND" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete task: {str(e)}"
        )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    limit: int = 100,
    offset: int = 0,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """List tasks with pagination.
    
    Args:
        limit: Maximum number of tasks to return
        offset: Offset for pagination
        client: Gateway messaging client
        
    Returns:
        List of tasks
        
    Raises:
        HTTPException: If listing fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        result = await client.list_tasks(
            limit=limit,
            offset=offset,
            user_id=user_id
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}"
        )


@router.post("/{task_id}/assign-users", response_model=dict)
async def assign_users_to_task(
    task_id: int,
    assign_data: TaskAssignUsers,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """Assign users to a task.
    
    Args:
        task_id: Task ID
        assign_data: User IDs to assign
        client: Gateway messaging client
        
    Returns:
        Assignment result
        
    Raises:
        HTTPException: If assignment fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        result = await client.assign_users_to_task(
            task_id=task_id,
            user_ids=assign_data.user_ids,
            user_id=user_id
        )
        return result
    except RuntimeError as e:
        if "NOT_FOUND" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign users: {str(e)}"
        )


@router.post("/{task_id}/assign-tags", response_model=dict)
async def assign_tags_to_task(
    task_id: int,
    assign_data: TaskAssignTags,
    client: GatewayMessagingClient = Depends(get_messaging_client)
):
    """Assign tags to a task.
    
    Args:
        task_id: Task ID
        assign_data: Tag IDs to assign
        client: Gateway messaging client
        
    Returns:
        Assignment result
        
    Raises:
        HTTPException: If assignment fails
    """
    try:
        # TODO: Get user_id from JWT token
        user_id = 1  # Placeholder
        
        result = await client.assign_tags_to_task(
            task_id=task_id,
            tag_ids=assign_data.tag_ids,
            user_id=user_id
        )
        return result
    except RuntimeError as e:
        if "NOT_FOUND" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign tags: {str(e)}"
        )


