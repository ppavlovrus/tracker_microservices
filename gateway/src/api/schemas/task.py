"""Task schemas for Gateway API."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    """Schema for creating a new task."""
    
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    status_id: int = Field(1, description="Task status ID (default: 1)")
    creator_id: int = Field(..., description="User ID who creates the task")
    deadline_start: Optional[date] = Field(None, description="Task start deadline")
    deadline_end: Optional[date] = Field(None, description="Task end deadline")
    
    @field_validator("deadline_end")
    @classmethod
    def validate_deadline_end(cls, v: Optional[date], info) -> Optional[date]:
        """Validate that deadline_end is after deadline_start."""
        if v and info.data.get("deadline_start"):
            if v < info.data["deadline_start"]:
                raise ValueError("deadline_end must be after deadline_start")
        return v


class TaskUpdate(BaseModel):
    """Schema for updating a task."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status_id: Optional[int] = None
    deadline_start: Optional[date] = None
    deadline_end: Optional[date] = None
    
    @field_validator("deadline_end")
    @classmethod
    def validate_deadline_end(cls, v: Optional[date], info) -> Optional[date]:
        """Validate that deadline_end is after deadline_start."""
        if v and info.data.get("deadline_start"):
            if v < info.data["deadline_start"]:
                raise ValueError("deadline_end must be after deadline_start")
        return v


class TaskResponse(BaseModel):
    """Schema for task response."""
    
    id: int
    title: str
    description: Optional[str] = None
    status_id: int
    creator_id: int
    deadline_start: Optional[date] = None
    deadline_end: Optional[date] = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """Schema for list of tasks response."""
    
    tasks: list[TaskResponse]
    total: int
    limit: int
    offset: int
