"""Task schemas for Gateway API."""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: str | None = Field(None, description="Task description")
    status_id: int = Field(1, description="Task status ID (default: 1)")
    creator_id: int = Field(..., description="User ID who creates the task")
    deadline_start: date | None = Field(None, description="Task start deadline")
    deadline_end: date | None = Field(None, description="Task end deadline")

    @field_validator("deadline_end")
    @classmethod
    def validate_deadline_end(cls, v: date | None, info) -> date | None:
        """Validate that deadline_end is after deadline_start."""
        if v and info.data.get("deadline_start"):
            if v < info.data["deadline_start"]:
                raise ValueError("deadline_end must be after deadline_start")
        return v


class TaskUpdate(BaseModel):
    """Schema for updating a task."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status_id: int | None = None
    deadline_start: date | None = None
    deadline_end: date | None = None

    @field_validator("deadline_end")
    @classmethod
    def validate_deadline_end(cls, v: date | None, info) -> date | None:
        """Validate that deadline_end is after deadline_start."""
        if v and info.data.get("deadline_start"):
            if v < info.data["deadline_start"]:
                raise ValueError("deadline_end must be after deadline_start")
        return v


class TaskTag(BaseModel):
    """A tag linked to a task."""

    id: int
    name: str


class TaskTagAdd(BaseModel):
    """Request to add a tag to a task by name (created if it doesn't exist)."""

    name: str = Field(..., min_length=1, max_length=100, description="Tag name")


class TaskResponse(BaseModel):
    """Schema for task response."""

    id: int
    title: str
    description: str | None = None
    status_id: int
    creator_id: int
    deadline_start: date | None = None
    deadline_end: date | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[TaskTag] = []


class TaskListResponse(BaseModel):
    """Schema for list of tasks response."""

    tasks: list[TaskResponse]
    total: int
    limit: int
    offset: int


class TaskStatsResponse(BaseModel):
    """Task counts per status for the Kanban column totals.

    ``by_status`` maps a status id to its task count; ``total`` is the count
    across all statuses. Counts cover the whole table, not just one list page.
    """

    total: int
    by_status: dict[int, int]
