from datetime import date
from enum import StrEnum

from pydantic import Field, ValidationInfo, field_validator

from .base import Contract


class TaskCommand(StrEnum):
    CREATE = "create_task"
    UPDATE = "update_task"
    DELETE = "delete_task"
    LIST = "list_tasks"
    STATS = "task_stats"
    ADD_TAG = "add_task_tag"
    REMOVE_TAG = "remove_task_tag"
    GET = "get_task"


class AttachmentCommand(StrEnum):
    CREATE = "create_attachment"
    GET = "get_attachment"
    DELETE = "delete_attachment"
    LIST = "list_attachments_by_task"


class CommentCommand(StrEnum):
    CREATE = "create_comment"
    GET = "get_comment"
    UPDATE = "update_comment"
    DELETE = "delete_comment"
    LIST = "list_comments_by_task"


class TagCommand(StrEnum):
    CREATE = "create_tag"
    GET = "get_tag"
    GET_BY_NAME = "get_tag_by_name"
    DELETE = "delete_tag"
    LIST = "list_tags"
    UPDATE = "update_tag"


class UserCommand(StrEnum):
    CREATE = "create_user"
    GET = "get_user"
    GET_BY_EMAIL = "get_user_by_email"
    GET_BY_USERNAME = "get_user_by_username"
    UPDATE = "update_user"
    DELETE = "delete_user"
    LIST = "list_users"
    UPSERT = "upsert_yandex_user"


class TaskCreationContract(Contract):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None
    status_id: int
    creator_id: int
    deadline_start: date | None
    deadline_end: date | None


class TaskUpdatePayloadContract(Contract):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status_id: int | None = None
    deadline_start: date | None = None
    deadline_end: date | None = None

    @field_validator("deadline_end")
    @classmethod
    def validate_deadline_end(cls, v: date | None, info: ValidationInfo) -> date | None:
        """Validate that deadline_end is after deadline_start."""
        if v and info.data.get("deadline_start") and v < info.data["deadline_start"]:
            raise ValueError("deadline_end must be after deadline_start")
        return v


class TaskUpdateContract(Contract):
    id: int = Field(..., gt=0)
    update: TaskUpdatePayloadContract


class TaskDeleteContract(Contract):
    id: int = Field(..., gt=0)


class TaskGetByIdContract(Contract):
    id: int = Field(..., gt=0)


class TaskAddTagContract(Contract):
    task_id: int = Field(..., gt=0)
    tag_id: int = Field(..., gt=0)


class TaskRemoveTagContract(Contract):
    task_id: int = Field(..., gt=0)
    tag_id: int = Field(..., gt=0)


class TaskListContract(Contract):
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)


class TaskStatsContract(Contract):
    """``task_stats`` takes no arguments: the payload is empty."""


# -- users ------------------------------------------------------------------
#
# Field bounds mirror the columns (username 64, email 255), not the HTTP
# schemas: the gateway may well demand more of its callers, but the bus
# contract describes what the worker can store.


class UserCreateContract(Contract):
    username: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., min_length=3, max_length=255)
    # Always a hash by the time it reaches the bus: plaintext passwords do
    # not leave the gateway.
    password_hash: str


class UserUpdatePayloadContract(Contract):
    username: str | None = Field(None, min_length=1, max_length=64)
    email: str | None = Field(None, min_length=3, max_length=255)
    password_hash: str | None = None


class UserUpdateContract(Contract):
    id: int = Field(..., gt=0)
    update: UserUpdatePayloadContract


class UserDeleteContract(Contract):
    id: int = Field(..., gt=0)


class UserGetByIdContract(Contract):
    id: int = Field(..., gt=0)


class UserGetByUsernameContract(Contract):
    username: str = Field(..., min_length=1, max_length=64)


class UserGetByEmailContract(Contract):
    email: str = Field(..., min_length=1, max_length=255)


class UserUpsertYandexContract(Contract):
    yandex_id: str = Field(..., min_length=1, max_length=64)
    login: str = Field(..., min_length=1, max_length=64)
    email: str = Field(..., min_length=1, max_length=255)


class UserListContract(Contract):
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
