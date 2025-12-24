"""Task schemas for Gateway API."""

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


class TaskStatusResponse(BaseModel):
    """Task status response."""
    id: int
    name: str


class TaskCreate(BaseModel):
    """Schema for creating a task."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status_id: int = Field(..., ge=1)
    deadline_start: Optional[date] = None
    deadline_end: Optional[date] = None


class TaskUpdate(BaseModel):
    """Schema for updating a task."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status_id: Optional[int] = Field(None, ge=1)
    deadline_start: Optional[date] = None
    deadline_end: Optional[date] = None


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: int
    title: str
    description: Optional[str]
    status_id: int
    creator_id: int
    deadline_start: Optional[date]
    deadline_end: Optional[date]
    created_at: datetime
    updated_at: datetime

