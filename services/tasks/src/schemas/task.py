"""User schemas (DTOs)."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

class TaskCreate(BaseModel):
    """Schema for creating a new task."""
    title: str = Field(..., min_length=3, max_length=255)
    description: str
    creator_id: int
    status_id: int
    deadline_start: Optional[datetime] = Field(None, min_length=10, max_length=10)
    deadline_end: Optional[datetime] = Field(None, min_length=10, max_length=10)

class TaskUpdate(BaseModel):
    """Schema for updating task (all fields optional)."""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    status_id: Optional[int] = Field(None, ge=0)
    deadline_start: Optional[datetime] = Field(None, min_length=10, max_length=10)
    deadline_end: Optional[datetime] = Field(None, min_length=10, max_length=10)
    assigned_to: Optional[int] = Field(None, ge=0)
    attachments: Optional[list[str]] = Field(None)
    tags: Optional[list[str]] = Field(None)

class TaskResponse(BaseModel):
    """Schema for a single task."""
    id: int
    title: str
    description: str

class TaskListResponse(BaseModel):
    """Schema for list of tasks."""
    items: List[TaskResponse]
