"""User schemas (DTOs)."""

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    title: str = Field(..., min_length=3, max_length=255)
    description: str
    creator_id: int
    status_id: int
    deadline_start: datetime | None = Field(None, min_length=10, max_length=10)
    deadline_end: datetime | None = Field(None, min_length=10, max_length=10)


class TaskUpdate(BaseModel):
    """Schema for updating task (all fields optional)."""

    title: str | None = Field(None, min_length=3, max_length=255)
    description: str | None = None
    status_id: int | None = Field(None, ge=0)
    deadline_start: datetime | None = Field(None, min_length=10, max_length=10)
    deadline_end: datetime | None = Field(None, min_length=10, max_length=10)
    assigned_to: int | None = Field(None, ge=0)
    attachments: list[str] | None = Field(None)
    tags: list[str] | None = Field(None)


class TaskResponse(BaseModel):
    """Schema for a single task."""

    id: int
    title: str
    description: str


class TaskListResponse(BaseModel):
    """Schema for list of tasks."""

    items: list[TaskResponse]
