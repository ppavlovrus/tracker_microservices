"""API schemas."""

from .task import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse
from .user import UserCreate, UserUpdate, UserResponse, UserListResponse

__all__ = [
    # Tasks
    "TaskCreate",
    "TaskUpdate",
    "TaskResponse",
    "TaskListResponse",
    # Users
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserListResponse",
]
