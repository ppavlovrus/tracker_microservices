"""API schemas."""

from .attachment import (
    AttachmentCreate,
    AttachmentInitiateResponse,
    AttachmentListResponse,
    AttachmentResponse,
)
from .comment import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
)
from .tags import TagCreate, TagListResponse, TagResponse, TagUpdate
from .task import TaskCreate, TaskListResponse, TaskResponse, TaskUpdate
from .user import UserCreate, UserListResponse, UserResponse, UserUpdate

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
