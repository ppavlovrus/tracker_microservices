from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from .base import Contract


class ErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    INTERNAL = "internal"


class RpcError(Contract):
    success: Literal[False]
    code: ErrorCode
    error: str
    error_type: str | None = None


class RpcOk[T](Contract):
    success: Literal[True]
    data: T


# A worker answer is one of the two, never a mix: ``success`` tells them apart,
# so pydantic picks the branch instead of guessing between them.
type RpcResponse[T] = Annotated[RpcOk[T] | RpcError, Field(discriminator="success")]


class TaskTag(Contract):
    id: int
    name: str


class TaskData(Contract):
    id: int
    title: str
    description: str | None
    status_id: int
    creator_id: int
    deadline_start: date | None
    deadline_end: date | None
    created_at: datetime
    updated_at: datetime
    tags: list[TaskTag]


class TaskDelete(Contract):
    id: int
    deleted: Literal[True]


class TaskList(Contract):
    total: int
    tasks: list[TaskData]


class TaskTags(Contract):
    """Payload of ``add_task_tag`` / ``remove_task_tag``: the task's tags after the change."""

    task_id: int
    tags: list[TaskTag]


# ``task_stats`` answers with {"total": n, "1": n, "2": n, "3": n}: a total plus one
# entry per status id, stringified for JSON transport. The per-status keys come from
# the data, not from the protocol, so pinning them here would freeze status ids into
# the contract — hence a mapping rather than a fixed model.
type TaskStats = dict[str, int]
