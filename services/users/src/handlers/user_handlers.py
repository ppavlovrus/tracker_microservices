"""User command handlers for RabbitMQ messages."""

import logging
from typing import Dict, Any

from ..repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserHandlers:
    """Handlers for user-related commands."""
    
    def __init__(self, repository: UserRepository):
        """
        Initialize handlers.
        
        Args:
            repository: UserRepository instance
        """
        self.repository = repository
    
    async def handle_create_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle create_user command.
        
        Args:
            data: User data from command
            
        Returns:
            Response with created user or error
        """
        try:
            # Check if email already exists
            existing_user = await self.repository.get_by_email(data.get("email"))
            if existing_user:
                return {
                    "success": False,
                    "error": "Email already exists"
                }
            
            # Create user
            user = await self.repository.create(data)
            
            # Convert timestamps to strings for JSON serialization
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()
            if user.get("updated_at"):
                user["updated_at"] = user["updated_at"].isoformat()
            
            logger.info(f"User created successfully: ID={user['id']}")
            
            return {
                "success": True,
                "data": user
            }
            
        except Exception as e:
            logger.error(f"Error creating user: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_user command.
        
        Args:
            data: Contains user ID
            
        Returns:
            Response with user data or error
        """
        try:
            user_id = data.get("id")
            
            if not user_id:
                return {
                    "success": False,
                    "error": "User ID is required"
                }
            
            user = await self.repository.get_by_id(user_id)
            
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }
            
            # Convert timestamps to strings for JSON
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()
            if user.get("updated_at"):
                user["updated_at"] = user["updated_at"].isoformat()
            
            logger.debug(f"User retrieved: ID={user_id}")
            
            return {
                "success": True,
                "data": user
            }
            
        except Exception as e:
            logger.error(f"Error getting user: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_get_user_by_email(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get_user_by_email command.
        
        Args:
            data: Contains email
            
        Returns:
            Response with user data or error
        """
        try:
            email = data.get("email")
            
            if not email:
                return {
                    "success": False,
                    "error": "Email is required"
                }
            
            user = await self.repository.get_by_email(email)
            
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }
            
            # Convert timestamps to strings for JSON
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()
            if user.get("updated_at"):
                user["updated_at"] = user["updated_at"].isoformat()
            
            logger.debug(f"User retrieved by email: {email}")
            
            return {
                "success": True,
                "data": user
            }
            
        except Exception as e:
            logger.error(f"Error getting user by email: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_update_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle update_user command.
        
        Args:
            data: Contains user ID and update fields
            
        Returns:
            Response with updated user or error
        """
        try:
            user_id = data.get("id")
            update_data = data.get("update", {})
            
            if not user_id:
                return {
                    "success": False,
                    "error": "User ID is required"
                }
            
            if not update_data:
                return {
                    "success": False,
                    "error": "No fields to update"
                }
            
            # If updating email, check if it's already taken
            if "email" in update_data:
                existing_user = await self.repository.get_by_email(update_data["email"])
                if existing_user and existing_user["id"] != user_id:
                    return {
                        "success": False,
                        "error": "Email already exists"
                    }
            
            # Update user
            user = await self.repository.update(user_id, update_data)
            
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }
            
            # Convert timestamps to strings for JSON
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()
            if user.get("updated_at"):
                user["updated_at"] = user["updated_at"].isoformat()
            
            logger.info(f"User updated successfully: ID={user_id}")
            
            return {
                "success": True,
                "data": user
            }
            
        except Exception as e:
            logger.error(f"Error updating user: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_delete_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle delete_user command.
        
        Args:
            data: Contains user ID
            
        Returns:
            Response indicating success or error
        """
        try:
            user_id = data.get("id")
            
            if not user_id:
                return {
                    "success": False,
                    "error": "User ID is required"
                }
            
            deleted = await self.repository.delete(user_id)
            
            if not deleted:
                return {
                    "success": False,
                    "error": "User not found"
                }
            
            logger.info(f"User deleted successfully: ID={user_id}")
            
            return {
                "success": True,
                "data": {"deleted": True, "id": user_id}
            }
            
        except Exception as e:
            logger.error(f"Error deleting user: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def handle_list_users(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle list_users command.
        
        Args:
            data: Contains limit and offset
            
        Returns:
            Response with list of users or error
        """
        try:
            limit = data.get("limit", 10)
            offset = data.get("offset", 0)
            
            # Get users and total count
            users = await self.repository.get_all(limit=limit, offset=offset)
            total = await self.repository.count_all()
            
            # Convert timestamps to strings for JSON
            for user in users:
                if user.get("created_at"):
                    user["created_at"] = user["created_at"].isoformat()
                if user.get("updated_at"):
                    user["updated_at"] = user["updated_at"].isoformat()
            
            logger.debug(f"Listed {len(users)} users (total={total}, limit={limit}, offset={offset})")
            
            return {
                "success": True,
                "data": {
                    "users": users,
                    "total": total
                }
            }
            
        except Exception as e:
            logger.error(f"Error listing users: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
