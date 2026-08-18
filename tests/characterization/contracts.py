"""Independent copies of the API contracts, as observed today.

Deliberately NOT imported from the gateway: a test that validates the app with
the app's own schema cannot notice when that schema changes. These duplicates
are the point -- when one of them needs an edit, the contract moved, and the
edit is the record of it.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Base for response contracts: an unexpected field is a contract change."""

    model_config = ConfigDict(extra="forbid")


class TagContract(Contract):
    id: int
    name: str


class TaskContract(Contract):
    id: int
    title: str
    description: str | None
    status_id: int
    creator_id: int
    deadline_start: date | None
    deadline_end: date | None
    created_at: datetime
    updated_at: datetime
    tags: list[TagContract]


class TaskListContract(Contract):
    tasks: list[TaskContract]
    total: int
    limit: int
    offset: int
