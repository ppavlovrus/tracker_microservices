"""Comment command handlers for RabbitMQ messages."""

import logging
from typing import Dict, Any

from ..repositories.comment_repository import CommentRepository

logger = logging.getLogger(__name__)


class CommentHandlers:
    """Handlers for comment-related commands."""
    
    def __init__(self, repository: CommentRepository):
        """
        Initialize handlers.
        
        Args:
            repository: CommentRepository instance
        """
        self.repository = repository
    
    async def handle_create_comment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle create_comment command.
        
        Args:
            data: Comment data from command
            
        Returns:
            Response with created comment or error
        """
        try:
            # Validate required fields
            if not data.get("task_id"):
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            if not data.get("user_id"):
                return {
                    "success": False,
                    "error": "User ID is required"
                }
            
            if not data.get("content"):
                return {
                    "success": False,
                    "error": "Content is required"
                }
            
            # Create comment
            comment = await self.repository.create(data)
            
            # Convert timestamps to strings for JSON serialization
            if comment.get("created_at"):
                comment["created_at"] = comment["created_at"].isoformat()
            if comment.get("updated_at"):
                comment["updated_at"] = comment["updated_at"].isoformat()
            
            logger.info(f"Comment created successfully: ID={comment['id']}")
            
            return {
                "success": True,
                "data": comment
            }
            
        except Exception as e:
            logger.error(f"Error creating comment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_comment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_comment command.
        
        Args:
            data: Contains comment ID
            
        Returns:
            Response with comment data or error
        """
        try:
            comment_id = data.get("id")
            
            if not comment_id:
                return {
                    "success": False,
                    "error": "Comment ID is required"
                }
            
            comment = await self.repository.get_by_id(comment_id)
            
            if not comment:
                return {
                    "success": False,
                    "error": "Comment not found"
                }
            
            # Convert timestamps to strings for JSON
            if comment.get("created_at"):
                comment["created_at"] = comment["created_at"].isoformat()
            if comment.get("updated_at"):
                comment["updated_at"] = comment["updated_at"].isoformat()
            
            logger.debug(f"Comment retrieved: ID={comment_id}")
            
            return {
                "success": True,
                "data": comment
            }
            
        except Exception as e:
            logger.error(f"Error getting comment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_update_comment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle update_comment command.
        
        Args:
            data: Contains comment ID and update fields
            
        Returns:
            Response with updated comment or error
        """
        try:
            comment_id = data.get("id")
            update_data = data.get("update", {})
            
            if not comment_id:
                return {
                    "success": False,
                    "error": "Comment ID is required"
                }
            
            if not update_data or not update_data.get("content"):
                return {
                    "success": False,
                    "error": "Content is required for update"
                }
            
            # Update comment
            comment = await self.repository.update(comment_id, update_data)
            
            if not comment:
                return {
                    "success": False,
                    "error": "Comment not found"
                }
            
            # Convert timestamps to strings for JSON
            if comment.get("created_at"):
                comment["created_at"] = comment["created_at"].isoformat()
            if comment.get("updated_at"):
                comment["updated_at"] = comment["updated_at"].isoformat()
            
            logger.info(f"Comment updated successfully: ID={comment_id}")
            
            return {
                "success": True,
                "data": comment
            }
            
        except Exception as e:
            logger.error(f"Error updating comment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_delete_comment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle delete_comment command.
        
        Args:
            data: Contains comment ID
            
        Returns:
            Response indicating success or error
        """
        try:
            comment_id = data.get("id")
            
            if not comment_id:
                return {
                    "success": False,
                    "error": "Comment ID is required"
                }
            
            deleted = await self.repository.delete(comment_id)
            
            if not deleted:
                return {
                    "success": False,
                    "error": "Comment not found"
                }
            
            logger.info(f"Comment deleted successfully: ID={comment_id}")
            
            return {
                "success": True,
                "data": {"deleted": True, "id": comment_id}
            }
            
        except Exception as e:
            logger.error(f"Error deleting comment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_list_comments_by_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle list_comments_by_task command.
        
        Args:
            data: Contains task_id
            
        Returns:
            Response with list of comments or error
        """
        try:
            task_id = data.get("task_id")
            
            if not task_id:
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            # Get comments and total count for task
            comments = await self.repository.get_by_task_id(task_id)
            total = await self.repository.count_by_task_id(task_id)
            
            # Convert timestamps to strings for JSON
            for comment in comments:
                if comment.get("created_at"):
                    comment["created_at"] = comment["created_at"].isoformat()
                if comment.get("updated_at"):
                    comment["updated_at"] = comment["updated_at"].isoformat()
            
            logger.debug(f"Listed {len(comments)} comments for task_id={task_id}")
            
            return {
                "success": True,
                "data": {
                    "comments": comments,
                    "total": total
                }
            }
            
        except Exception as e:
            logger.error(f"Error listing comments: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
