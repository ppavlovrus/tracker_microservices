"""Task command handlers for RabbitMQ messages."""

import logging
from typing import Dict, Any
from datetime import date

from ..repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)


class TaskHandlers:
    """Handlers for task-related commands."""
    
    def __init__(self, repository: TaskRepository):
        """
        Initialize handlers.
        
        Args:
            repository: TaskRepository instance
        """
        self.repository = repository
    
    async def handle_create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle create_task command.
        
        Args:
            data: Task data from command
            
        Returns:
            Response with created task or error
        """
        try:
            # Convert date strings to date objects if needed
            if "deadline_start" in data and isinstance(data["deadline_start"], str):
                data["deadline_start"] = date.fromisoformat(data["deadline_start"])
            if "deadline_end" in data and isinstance(data["deadline_end"], str):
                data["deadline_end"] = date.fromisoformat(data["deadline_end"])
            
            # Create task
            task = await self.repository.create(data)
            
            # Convert dates back to strings for JSON serialization
            if task.get("deadline_start"):
                task["deadline_start"] = task["deadline_start"].isoformat()
            if task.get("deadline_end"):
                task["deadline_end"] = task["deadline_end"].isoformat()
            if task.get("created_at"):
                task["created_at"] = task["created_at"].isoformat()
            if task.get("updated_at"):
                task["updated_at"] = task["updated_at"].isoformat()
            
            logger.info(f"Task created successfully: ID={task['id']}")
            
            return {
                "success": True,
                "data": task
            }
            
        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_task command.
        
        Args:
            data: Contains task ID
            
        Returns:
            Response with task data or error
        """
        try:
            task_id = data.get("id")
            
            if not task_id:
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            task = await self.repository.get_by_id(task_id)
            
            if not task:
                return {
                    "success": False,
                    "error": "Task not found"
                }
            
            # Convert dates to strings for JSON
            if task.get("deadline_start"):
                task["deadline_start"] = task["deadline_start"].isoformat()
            if task.get("deadline_end"):
                task["deadline_end"] = task["deadline_end"].isoformat()
            if task.get("created_at"):
                task["created_at"] = task["created_at"].isoformat()
            if task.get("updated_at"):
                task["updated_at"] = task["updated_at"].isoformat()
            
            logger.debug(f"Task retrieved: ID={task_id}")
            
            return {
                "success": True,
                "data": task
            }
            
        except Exception as e:
            logger.error(f"Error getting task: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_update_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle update_task command.
        
        Args:
            data: Contains task ID and update fields
            
        Returns:
            Response with updated task or error
        """
        try:
            task_id = data.get("id")
            update_data = data.get("update", {})
            
            if not task_id:
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            if not update_data:
                return {
                    "success": False,
                    "error": "No fields to update"
                }
            
            # Convert date strings to date objects if needed
            if "deadline_start" in update_data and isinstance(update_data["deadline_start"], str):
                update_data["deadline_start"] = date.fromisoformat(update_data["deadline_start"])
            if "deadline_end" in update_data and isinstance(update_data["deadline_end"], str):
                update_data["deadline_end"] = date.fromisoformat(update_data["deadline_end"])
            
            # Update task
            task = await self.repository.update(task_id, update_data)
            
            if not task:
                return {
                    "success": False,
                    "error": "Task not found"
                }
            
            # Convert dates to strings for JSON
            if task.get("deadline_start"):
                task["deadline_start"] = task["deadline_start"].isoformat()
            if task.get("deadline_end"):
                task["deadline_end"] = task["deadline_end"].isoformat()
            if task.get("created_at"):
                task["created_at"] = task["created_at"].isoformat()
            if task.get("updated_at"):
                task["updated_at"] = task["updated_at"].isoformat()
            
            logger.info(f"Task updated successfully: ID={task_id}")
            
            return {
                "success": True,
                "data": task
            }
            
        except Exception as e:
            logger.error(f"Error updating task: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_delete_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle delete_task command.
        
        Args:
            data: Contains task ID
            
        Returns:
            Response indicating success or error
        """
        try:
            task_id = data.get("id")
            
            if not task_id:
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            deleted = await self.repository.delete(task_id)
            
            if not deleted:
                return {
                    "success": False,
                    "error": "Task not found"
                }
            
            logger.info(f"Task deleted successfully: ID={task_id}")
            
            return {
                "success": True,
                "data": {"deleted": True, "id": task_id}
            }
            
        except Exception as e:
            logger.error(f"Error deleting task: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_list_tasks(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle list_tasks command.
        
        Args:
            data: Contains limit and offset
            
        Returns:
            Response with list of tasks or error
        """
        try:
            limit = data.get("limit", 10)
            offset = data.get("offset", 0)
            
            # Get tasks and total count
            tasks = await self.repository.get_all(limit=limit, offset=offset)
            total = await self.repository.count_all()
            
            # Convert dates to strings for JSON
            for task in tasks:
                if task.get("deadline_start"):
                    task["deadline_start"] = task["deadline_start"].isoformat()
                if task.get("deadline_end"):
                    task["deadline_end"] = task["deadline_end"].isoformat()
                if task.get("created_at"):
                    task["created_at"] = task["created_at"].isoformat()
                if task.get("updated_at"):
                    task["updated_at"] = task["updated_at"].isoformat()
            
            logger.debug(f"Listed {len(tasks)} tasks (total={total}, limit={limit}, offset={offset})")
            
            return {
                "success": True,
                "data": {
                    "tasks": tasks,
                    "total": total
                }
            }
            
        except Exception as e:
            logger.error(f"Error listing tasks: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
