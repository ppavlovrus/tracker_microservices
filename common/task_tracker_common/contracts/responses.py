from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field

from .base import Contract


class ErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    CONFLICT = "conflict"
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


class UserData(Contract):
    """A user as the rest of the platform is allowed to see one.

    No ``password_hash`` field, on purpose: with ``extra="forbid"`` a worker
    that leaks the hash into a public answer fails validation inside the
    worker instead of relying on the gateway to remember to strip it.
    """

    id: int
    username: str
    email: str
    created_at: datetime
    updated_at: datetime


class UserAccount(Contract):
    """The auth flows' view of a user: carries the credentials.

    Only two commands may answer with this -- the login lookup and the OAuth
    upsert -- and their payloads exist to be verified against, never to be
    forwarded. ``password_hash`` is nullable because OAuth-backed users have
    no local password.
    """

    id: int
    username: str
    email: str
    password_hash: str | None
    yandex_id: str | None = None
    created_at: datetime
    last_login: datetime | None = None


class UserDelete(Contract):
    id: int
    deleted: Literal[True]


class UserList(Contract):
    total: int
    users: list[UserData]


# ``task_stats`` answers with {"total": n, "1": n, "2": n, "3": n}: a total plus one
# entry per status id, stringified for JSON transport. The per-status keys come from
# the data, not from the protocol, so pinning them here would freeze status ids into
# the contract — hence a mapping rather than a fixed model.
type TaskStats = dict[str, int]


def rpc_ok(contract: Any, data: Any) -> dict[str, Any]:
    """Build the success envelope for the wire, validating ``data`` on the way out.

    ``contract`` is the payload shape this command promises (``TaskData``,
    ``TaskList``, ...). Validating here, rather than trusting whatever the
    repository handed back, means a handler that drifts from its contract fails
    inside the worker where the traceback still points at the query that
    produced the row -- instead of surfacing as a shape error in the gateway,
    one process and one queue away.
    """
    return RpcOk[contract](success=True, data=data).model_dump(mode="json")


def rpc_error(code: ErrorCode, message: str, error_type: str | None = None) -> dict[str, Any]:
    """Build the failure envelope for the wire.

    ``code`` is the field callers branch on; ``message`` is for humans reading
    logs and must never be the only thing carrying meaning.
    """
    return RpcError(success=False, code=code, error=message, error_type=error_type).model_dump(mode="json")
