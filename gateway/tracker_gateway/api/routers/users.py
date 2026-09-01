"""Users router for Gateway API.

HTTP in, HTTP out. Passwords are hashed in the service layer, errors become
statuses in ``api/errors.py``, and the wire lives in the bus client -- which
is why there is not a single try/except left in this file.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Path, Query
from task_tracker_common.contracts.base import INT4_MAX

from ..deps import UsersServiceDep
from ..schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

UserId = Annotated[int, Path(ge=1, le=INT4_MAX)]


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate, service: UsersServiceDep) -> UserResponse:
    """
    Create a new user (registration).

    - **username**: 3-50 characters
    - **email**: Valid email address
    - **password**: 8-100 characters (will be hashed)
    """
    created = await service.register(username=user.username, email=user.email, password=user.password)
    return UserResponse(**created.model_dump())


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UserId, service: UsersServiceDep) -> UserResponse:
    """
    Get user by ID.

    Returns user data without password hash.
    """
    found = await service.get(user_id)
    return UserResponse(**found.model_dump())


@router.get("", response_model=UserListResponse)
async def list_users(
    service: UsersServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    """
    List users with pagination.

    Returns users without password hashes.
    """
    page = await service.list_users(limit=limit, offset=offset)

    return UserListResponse(
        users=[UserResponse(**user.model_dump()) for user in page.users],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UserId, user: UserUpdate, service: UsersServiceDep) -> UserResponse:
    """
    Update user by ID.

    - **username**: Optional, 3-50 characters
    - **email**: Optional, valid email address
    - **password**: Optional, 8-100 characters (will be hashed)
    """
    updated = await service.update(user_id, user.model_dump(exclude_unset=True))
    return UserResponse(**updated.model_dump())


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: UserId, service: UsersServiceDep) -> None:
    """
    Delete user by ID.

    This will permanently delete the user.
    """
    await service.delete(user_id)
