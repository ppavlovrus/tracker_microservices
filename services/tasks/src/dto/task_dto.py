from pydantic import Field, BaseModel
from enum import Enum
from typing import Optional, List
from datetime import date

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

    deadline_start: Optional[str]
    deadline_end: Optional[str]

    assigned_to: Optional[int] = Field(int, ge=0)
    attachments: Optional[list[str]] = Field(list[str])
    tags: Optional[list[str]] = Field(list[str])


