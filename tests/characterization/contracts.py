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


class UserContract(Contract):
    """A user as the /users endpoints answer it. ``extra="forbid"`` is the
    assertion that matters most here: password_hash showing up in a response
    would fail validation instead of passing silently."""

    id: int
    username: str
    email: str
    created_at: datetime
    updated_at: datetime


class UserListContract(Contract):
    users: list[UserContract]
    total: int
    limit: int
    offset: int


class UserPublicContract(Contract):
    """The trimmed user inside a login answer."""

    id: int
    username: str
    email: str | None


class LoginResponseContract(Contract):
    user: UserPublicContract


class StatsContract(Contract):
    total: int
    # Keys are strings on purpose: the gateway builds dict[int, int], but JSON has
    # no numeric keys, so the client sees {"1": n}. Declaring dict[int, int] here
    # would make Pydantic coerce them back and hide what crosses the wire.
    by_status: dict[str, int]
