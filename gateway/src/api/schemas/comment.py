"""Comment schemas for Gateway API."""

from datetime import datetime
from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    """Schema for creating a new comment."""

    task_id: int = Field(..., description="Task the comment belongs to")
    user_id: int = Field(..., description="Author user ID")
    content: str = Field(..., min_length=1, description="Comment text")


class CommentUpdate(BaseModel):
    """Schema for updating a comment."""

    content: str = Field(..., min_length=1, description="Comment text")


class CommentResponse(BaseModel):
    """Schema for comment response."""

    id: int
    task_id: int
    user_id: int
    content: str
    created_at: datetime
    updated_at: datetime


class CommentListResponse(BaseModel):
    """Schema for list of comments response."""

    comments: list[CommentResponse]
    total: int
