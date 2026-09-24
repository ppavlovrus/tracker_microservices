"""Task schemas for Gateway API."""

from datetime import date, datetime

from pydantic import BaseModel, Field, ValidationInfo, field_validator
from task_tracker_common.contracts.base import FreeText, RowId, TaskStatusId

from .partial import PartialUpdate, reject_null


def _deadline_end_after_start(v: date | None, info: ValidationInfo) -> date | None:
    """Validate that deadline_end is after deadline_start."""
    if v and info.data.get("deadline_start") and v < info.data["deadline_start"]:
        raise ValueError("deadline_end must be after deadline_start")
    return v


class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: FreeText | None = Field(None, description="Task description")
    status_id: TaskStatusId = Field(TaskStatusId.TODO, description="Task status ID")
    creator_id: RowId = Field(..., description="User ID who creates the task")
    deadline_start: date | None = Field(None, description="Task start deadline")
    deadline_end: date | None = Field(None, description="Task end deadline")

    _check_deadline = field_validator("deadline_end")(_deadline_end_after_start)


class TaskUpdate(PartialUpdate):
    """Schema for updating a task.

    Every field is optional, but the ones backing a NOT NULL column may not be
    set to null: ``title`` and ``status_id`` can be changed or left alone,
    never blanked. The deadlines and the description can be cleared, because
    those columns are nullable.
    """

    title: str | None = Field(None, min_length=1, max_length=255)
    description: FreeText | None = None
    status_id: TaskStatusId | None = None
    deadline_start: date | None = None
    deadline_end: date | None = None

    _check_deadline = field_validator("deadline_end")(_deadline_end_after_start)

    @field_validator("title", "status_id")
    @classmethod
    def _not_nullable(cls, v: object) -> object:
        return reject_null(v)


class TaskTag(BaseModel):
    """A tag linked to a task."""

    id: int
    name: str


class TaskTagAdd(BaseModel):
    """Request to add a tag to a task by name (created if it doesn't exist)."""

    name: str = Field(..., min_length=1, max_length=100, description="Tag name")


class TaskResponse(BaseModel):
    """Schema for task response.

    ``status_id`` stays a plain int here on purpose: a status added by a later
    migration must not make an existing row unreadable on the way out.
    """

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
