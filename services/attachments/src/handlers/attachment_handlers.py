"""Attachment command handlers for RabbitMQ messages."""

import logging
from typing import Dict, Any

from ..repositories.attachment_repository import AttachmentRepository

logger = logging.getLogger(__name__)


class AttachmentHandlers:
    """Handlers for attachment-related commands."""
    
    def __init__(self, repository: AttachmentRepository):
        """
        Initialize handlers.
        
        Args:
            repository: AttachmentRepository instance
        """
        self.repository = repository
    
    async def handle_create_attachment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle create_attachment command.
        
        Args:
            data: Attachment data from command
            
        Returns:
            Response with created attachment or error
        """
        try:
            # Validate required fields
            if not data.get("task_id"):
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            if not data.get("filename"):
                return {
                    "success": False,
                    "error": "Filename is required"
                }
            
            if not data.get("storage_path"):
                return {
                    "success": False,
                    "error": "Storage path is required"
                }
            
            # Create attachment
            attachment = await self.repository.create(data)
            
            # Convert timestamp to string for JSON serialization
            if attachment.get("uploaded_at"):
                attachment["uploaded_at"] = attachment["uploaded_at"].isoformat()
            
            logger.info(f"Attachment created successfully: ID={attachment['id']}")
            
            return {
                "success": True,
                "data": attachment
            }
            
        except Exception as e:
            logger.error(f"Error creating attachment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_attachment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_attachment command.
        
        Args:
            data: Contains attachment ID
            
        Returns:
            Response with attachment data or error
        """
        try:
            attachment_id = data.get("id")
            
            if not attachment_id:
                return {
                    "success": False,
                    "error": "Attachment ID is required"
                }
            
            attachment = await self.repository.get_by_id(attachment_id)
            
            if not attachment:
                return {
                    "success": False,
                    "error": "Attachment not found"
                }
            
            # Convert timestamp to string for JSON
            if attachment.get("uploaded_at"):
                attachment["uploaded_at"] = attachment["uploaded_at"].isoformat()
            
            logger.debug(f"Attachment retrieved: ID={attachment_id}")
            
            return {
                "success": True,
                "data": attachment
            }
            
        except Exception as e:
            logger.error(f"Error getting attachment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_delete_attachment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle delete_attachment command.
        
        Args:
            data: Contains attachment ID
            
        Returns:
            Response indicating success or error
        """
        try:
            attachment_id = data.get("id")
            
            if not attachment_id:
                return {
                    "success": False,
                    "error": "Attachment ID is required"
                }
            
            deleted = await self.repository.delete(attachment_id)
            
            if not deleted:
                return {
                    "success": False,
                    "error": "Attachment not found"
                }
            
            logger.info(f"Attachment deleted successfully: ID={attachment_id}")
            
            return {
                "success": True,
                "data": {"deleted": True, "id": attachment_id}
            }
            
        except Exception as e:
            logger.error(f"Error deleting attachment: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_list_attachments_by_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle list_attachments_by_task command.
        
        Args:
            data: Contains task_id
            
        Returns:
            Response with list of attachments or error
        """
        try:
            task_id = data.get("task_id")
            
            if not task_id:
                return {
                    "success": False,
                    "error": "Task ID is required"
                }
            
            # Get attachments and total count for task
            attachments = await self.repository.get_by_task_id(task_id)
            total = await self.repository.count_by_task_id(task_id)
            
            # Convert timestamps to strings for JSON
            for attachment in attachments:
                if attachment.get("uploaded_at"):
                    attachment["uploaded_at"] = attachment["uploaded_at"].isoformat()
            
            logger.debug(f"Listed {len(attachments)} attachments for task_id={task_id}")
            
            return {
                "success": True,
                "data": {
                    "attachments": attachments,
                    "total": total
                }
            }
            
        except Exception as e:
            logger.error(f"Error listing attachments: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
