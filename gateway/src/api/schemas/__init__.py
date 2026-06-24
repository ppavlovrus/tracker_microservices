"""API schemas."""

from .task import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse
from .user import UserCreate, UserUpdate, UserResponse, UserListResponse
from .comment import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
)
from .tags import TagCreate, TagUpdate, TagResponse, TagListResponse
from .attachment import (
    AttachmentCreate,
    AttachmentResponse,
    AttachmentInitiateResponse,
    AttachmentListResponse,
)

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
    # Comments
    "CommentCreate",
    "CommentUpdate",
    "CommentResponse",
    "CommentListResponse",
    # Tags
    "TagCreate",
    "TagUpdate",
    "TagResponse",
    "TagListResponse",
    # Attachments
    "AttachmentCreate",
    "AttachmentResponse",
    "AttachmentInitiateResponse",
    "AttachmentListResponse",
]
