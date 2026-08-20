from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    TO_DO = "TO_DO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class Task(BaseModel):
    id: int
    title: str = Field(str, min_length=1, max_length=255)
    description: str
    creator_id: int
    status: TaskStatus

    deadline_start: str | None
    deadline_end: str | None

    assigned_to: int | None = Field(int, ge=0)
    attachments: list[str] | None = Field(list[str])
    tags: list[str] | None = Field(list[str])
