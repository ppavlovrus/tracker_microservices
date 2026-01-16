"""Users router for Gateway API."""

import logging
import bcrypt
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated

from ...config import RPC_TIMEOUT
from ..schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def remove_password_hash(user_data: dict) -> dict:
    """
    Remove password_hash from user data before sending to client.
    
    Args:
        user_data: User data dict
        
    Returns:
        User data without password_hash
    """
    user_copy = user_data.copy()
    user_copy.pop('password_hash', None)
    return user_copy


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate) -> UserResponse:
    """
    Create a new user (registration).
    
    - **username**: 3-50 characters
    - **email**: Valid email address
    - **password**: 8-100 characters (will be hashed)
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Hash password before sending to Users Service
        password_hash = hash_password(user.password)
        
        # Send RPC command to Users service
        response = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "create_user",
                "data": {
                    "username": user.username,
                    "email": user.email,
                    "password_hash": password_hash
                }
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to create user: {error_msg}")
            
            # Return appropriate HTTP status
            if "already exists" in error_msg.lower():
                raise HTTPException(status_code=409, detail=error_msg)
            
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Remove password_hash from response before sending to client
        user_data = remove_password_hash(response["data"])
        
        logger.info(f"User created successfully: {user_data.get('id')}")
        return UserResponse(**user_data)
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Users service response")
        raise HTTPException(
            status_code=504,
            detail="Users service timeout"
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int) -> UserResponse:
    """
    Get user by ID.
    
    Returns user data without password hash.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Send RPC command to Users service
        response = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "get_user",
                "data": {"id": user_id}
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "User not found")
            logger.warning(f"User {user_id} not found")
            raise HTTPException(status_code=404, detail=error_msg)
        
        # Remove password_hash from response
        user_data = remove_password_hash(response["data"])
        
        logger.debug(f"User {user_id} retrieved successfully")
        return UserResponse(**user_data)
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Users service response")
        raise HTTPException(
            status_code=504,
            detail="Users service timeout"
        )
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=UserListResponse)
async def list_users(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0
) -> UserListResponse:
    """
    List users with pagination.
    
    Returns users without password hashes.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Send RPC command to Users service
        response = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "list_users",
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
            logger.error(f"Failed to list users: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        data = response["data"]
        
        # Remove password_hash from all users
        users_clean = [remove_password_hash(user) for user in data["users"]]
        users = [UserResponse(**user) for user in users_clean]
        
        logger.debug(f"Listed {len(users)} users (limit={limit}, offset={offset})")
        return UserListResponse(
            users=users,
            total=data.get("total", len(users)),
            limit=limit,
            offset=offset
        )
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Users service response")
        raise HTTPException(
            status_code=504,
            detail="Users service timeout"
        )
    except Exception as e:
        logger.error(f"Error listing users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate) -> UserResponse:
    """
    Update user by ID.
    
    - **username**: Optional, 3-50 characters
    - **email**: Optional, valid email address
    - **password**: Optional, 8-100 characters (will be hashed)
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Prepare update data
        update_data = user.model_dump(exclude_unset=True)
        
        # Hash password if provided
        if "password" in update_data:
            update_data["password_hash"] = hash_password(update_data.pop("password"))
        
        # Send RPC command to Users service
        response = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "update_user",
                "data": {
                    "id": user_id,
                    "update": update_data
                }
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "User not found")
            logger.warning(f"Failed to update user {user_id}: {error_msg}")
            
            # Return appropriate HTTP status
            if "not found" in error_msg.lower():
                raise HTTPException(status_code=404, detail=error_msg)
            elif "already exists" in error_msg.lower():
                raise HTTPException(status_code=409, detail=error_msg)
            
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Remove password_hash from response
        user_data = remove_password_hash(response["data"])
        
        logger.info(f"User {user_id} updated successfully")
        return UserResponse(**user_data)
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Users service response")
        raise HTTPException(
            status_code=504,
            detail="Users service timeout"
        )
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int) -> None:
    """
    Delete user by ID.
    
    This will permanently delete the user.
    """
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    try:
        # Send RPC command to Users service
        response = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "delete_user",
                "data": {"id": user_id}
            },
            timeout=RPC_TIMEOUT
        )
        
        # Check response
        if not response.get("success"):
            error_msg = response.get("error", "User not found")
            logger.warning(f"Failed to delete user {user_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)
        
        logger.info(f"User {user_id} deleted successfully")
        
    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Users service response")
        raise HTTPException(
            status_code=504,
            detail="Users service timeout"
        )
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
