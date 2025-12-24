"""Task schemas (DTOs)."""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, model_validator


class TaskCreate(BaseModel):
    """Schema for creating a new task."""
    
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None  # Nullable в БД
    status_id: int = Field(..., ge=1)
    creator_id: int = Field(..., ge=1)
    deadline_start: Optional[date] = None  # Date, не datetime!
    deadline_end: Optional[date] = None

    @model_validator(mode='after')
    def validate_deadlines(self):
        """Validate that deadline_end is after deadline_start."""
        if self.deadline_start and self.deadline_end:
            if self.deadline_end < self.deadline_start:
                raise ValueError("deadline_end must be after or equal to deadline_start")
        return self


class TaskUpdate(BaseModel):
    """Schema for updating task (all fields optional)."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status_id: Optional[int] = Field(None, ge=1)
    deadline_start: Optional[date] = None
    deadline_end: Optional[date] = None


    @model_validator(mode='after')
    def validate_deadlines(self):
        """Validate that deadline_end is after deadline_start."""
        if self.deadline_start and self.deadline_end:
            if self.deadline_end < self.deadline_start:
                raise ValueError("deadline_end must be after or equal to deadline_start")
        return self


class TaskResponse(BaseModel):
    """Schema for a single task."""
    
    id: int
    title: str
    description: Optional[str]
    status_id: int
    creator_id: int
    deadline_start: Optional[date]
    deadline_end: Optional[date]
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """Schema for list of tasks."""
    
    items: List[TaskResponse]
    limit: int
    offset: int


class TaskAssignUsersRequest(BaseModel):
    """Schema for assigning users to task."""
    
    user_ids: List[int] = Field(..., description="List of user IDs to assign")


class TaskAssignTagsRequest(BaseModel):
    """Schema for assigning tags to task."""
    
    tag_ids: List[int] = Field(..., description="List of tag IDs to assign")

class TaskStatusCreate(BaseModel):
    """Schema for creating task status."""
    
    name: str = Field(..., min_length=1, max_length=50)


class TaskStatusUpdate(BaseModel):
    """Schema for updating task status."""
    
    name: str = Field(..., min_length=1, max_length=50)


class TaskStatusResponse(BaseModel):
    """Schema for task status."""
    
    id: int
    name: str


class TaskStatusListResponse(BaseModel):
    """Schema for list of task statuses."""
    
    items: List[TaskStatusResponse]
