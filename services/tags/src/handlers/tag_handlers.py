"""Tag command handlers for RabbitMQ messages."""

import logging
from typing import Dict, Any

from ..repositories.tag_repository import TagRepository

logger = logging.getLogger(__name__)


class TagHandlers:
    """Handlers for tag-related commands."""
    
    def __init__(self, repository: TagRepository):
        """
        Initialize handlers.
        
        Args:
            repository: TagRepository instance
        """
        self.repository = repository
    
    async def handle_create_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle create_tag command.
        
        Args:
            data: Tag data from command
            
        Returns:
            Response with created tag or error
        """
        try:
            # Validate required fields
            if not data.get("name"):
                return {
                    "success": False,
                    "error": "Tag name is required"
                }
            
            # Check if tag with this name already exists
            existing_tag = await self.repository.get_by_name(data.get("name"))
            if existing_tag:
                return {
                    "success": False,
                    "error": "Tag with this name already exists"
                }
            
            # Create tag
            tag = await self.repository.create(data)
            
            logger.info(f"Tag created successfully: ID={tag['id']}")
            
            return {
                "success": True,
                "data": tag
            }
            
        except Exception as e:
            logger.error(f"Error creating tag: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_tag command.
        
        Args:
            data: Contains tag ID
            
        Returns:
            Response with tag data or error
        """
        try:
            tag_id = data.get("id")
            
            if not tag_id:
                return {
                    "success": False,
                    "error": "Tag ID is required"
                }
            
            tag = await self.repository.get_by_id(tag_id)
            
            if not tag:
                return {
                    "success": False,
                    "error": "Tag not found"
                }
            
            logger.debug(f"Tag retrieved: ID={tag_id}")
            
            return {
                "success": True,
                "data": tag
            }
            
        except Exception as e:
            logger.error(f"Error getting tag: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_tag_by_name(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_tag_by_name command.
        
        Args:
            data: Contains tag name
            
        Returns:
            Response with tag data or error
        """
        try:
            name = data.get("name")
            
            if not name:
                return {
                    "success": False,
                    "error": "Tag name is required"
                }
            
            tag = await self.repository.get_by_name(name)
            
            if not tag:
                return {
                    "success": False,
                    "error": "Tag not found"
                }
            
            logger.debug(f"Tag retrieved by name: {name}")
            
            return {
                "success": True,
                "data": tag
            }
            
        except Exception as e:
            logger.error(f"Error getting tag by name: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_update_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle update_tag command.
        
        Args:
            data: Contains tag ID and update fields
            
        Returns:
            Response with updated tag or error
        """
        try:
            tag_id = data.get("id")
            update_data = data.get("update", {})
            
            if not tag_id:
                return {
                    "success": False,
                    "error": "Tag ID is required"
                }
            
            if not update_data or not update_data.get("name"):
                return {
                    "success": False,
                    "error": "Tag name is required for update"
                }
            
            # Check if new name already exists (for another tag)
            existing_tag = await self.repository.get_by_name(update_data["name"])
            if existing_tag and existing_tag["id"] != tag_id:
                return {
                    "success": False,
                    "error": "Tag with this name already exists"
                }
            
            # Update tag
            tag = await self.repository.update(tag_id, update_data)
            
            if not tag:
                return {
                    "success": False,
                    "error": "Tag not found"
                }
            
            logger.info(f"Tag updated successfully: ID={tag_id}")
            
            return {
                "success": True,
                "data": tag
            }
            
        except Exception as e:
            logger.error(f"Error updating tag: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_delete_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle delete_tag command.
        
        Args:
            data: Contains tag ID
            
        Returns:
            Response indicating success or error
        """
        try:
            tag_id = data.get("id")
            
            if not tag_id:
                return {
                    "success": False,
                    "error": "Tag ID is required"
                }
            
            deleted = await self.repository.delete(tag_id)
            
            if not deleted:
                return {
                    "success": False,
                    "error": "Tag not found"
                }
            
            logger.info(f"Tag deleted successfully: ID={tag_id}")
            
            return {
                "success": True,
                "data": {"deleted": True, "id": tag_id}
            }
            
        except Exception as e:
            logger.error(f"Error deleting tag: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_list_tags(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle list_tags command.
        
        Args:
            data: Contains limit and offset
            
        Returns:
            Response with list of tags or error
        """
        try:
            limit = data.get("limit", 100)
            offset = data.get("offset", 0)
            
            # Get tags and total count
            tags = await self.repository.get_all(limit=limit, offset=offset)
            total = await self.repository.count_all()
            
            logger.debug(f"Listed {len(tags)} tags (total={total}, limit={limit}, offset={offset})")
            
            return {
                "success": True,
                "data": {
                    "tags": tags,
                    "total": total
                }
            }
            
        except Exception as e:
            logger.error(f"Error listing tags: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
