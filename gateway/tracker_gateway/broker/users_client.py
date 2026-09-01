"""Typed access to the users service over the RPC bus.

Everything that knows the wire lives here: the queue, the command names, the
payload contracts and the envelope. A caller gets a validated contract back or
an exception -- never a dict to poke at with ``.get()``, and never an HTTP
status, which belongs to the layer above and is none of this layer's business.

Two return shapes, on purpose. ``UserData`` is what almost every caller gets.
``UserAccount`` -- the one with ``password_hash`` -- comes back only from
``get_by_username`` and ``upsert_yandex``, the two auth lookups whose whole
job is to verify or establish credentials. Nothing else can even ask for it.
"""

import logging
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from task_tracker_common.contracts.commands import (
    UserCommand,
    UserCreateContract,
    UserDeleteContract,
    UserGetByIdContract,
    UserGetByUsernameContract,
    UserListContract,
    UserUpdateContract,
    UserUpdatePayloadContract,
    UserUpsertYandexContract,
)
from task_tracker_common.contracts.queues import Queue
from task_tracker_common.contracts.responses import (
    ErrorCode,
    RpcError,
    RpcResponse,
    UserAccount,
    UserData,
    UserDelete,
    UserList,
)

from ..config import RPC_TIMEOUT
from ..core.exceptions import (
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    EmailTakenError,
    UpstreamFailureError,
    UsernameTakenError,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)


class UsersBusClient:
    """The users service, as seen from the gateway."""

    def __init__(self, rabbitmq_client: Any, timeout: float = RPC_TIMEOUT) -> None:
        """Wrap a connected RabbitMQ client; ``None`` is allowed and answers BusUnavailableError."""
        self._rabbitmq = rabbitmq_client
        self._timeout = timeout

    # -- commands ---------------------------------------------------------

    async def create(self, user: UserCreateContract) -> UserData:
        """Create a user and return it as stored."""
        return await self._call(UserCommand.CREATE, user, UserData)

    async def get(self, user_id: int) -> UserData:
        """Return one user, or raise UserNotFoundError."""
        return await self._call(UserCommand.GET, UserGetByIdContract(id=user_id), UserData, user_id=user_id)

    async def get_by_username(self, username: str) -> UserAccount:
        """Return the credential record for a username, or raise UserNotFoundError."""
        request = UserGetByUsernameContract(username=username)
        return await self._call(UserCommand.GET_BY_USERNAME, request, UserAccount)

    async def upsert_yandex(self, identity: UserUpsertYandexContract) -> UserAccount:
        """Resolve a Yandex identity to a local user, creating or linking one."""
        return await self._call(UserCommand.UPSERT, identity, UserAccount)

    async def update(self, user_id: int, update: UserUpdatePayloadContract) -> UserData:
        """Apply a partial update and return the user as stored."""
        request = UserUpdateContract(id=user_id, update=update)
        # The only call that excludes unset fields, and it has to: a partial
        # update is defined by which fields the caller named.
        return await self._call(UserCommand.UPDATE, request, UserData, user_id=user_id, exclude_unset=True)

    async def delete(self, user_id: int) -> UserDelete:
        """Delete a user, or raise UserNotFoundError if it was not there."""
        return await self._call(UserCommand.DELETE, UserDeleteContract(id=user_id), UserDelete, user_id=user_id)

    async def list_users(self, limit: int, offset: int) -> UserList:
        """Return one page of users plus the count over the whole table."""
        return await self._call(UserCommand.LIST, UserListContract(limit=limit, offset=offset), UserList)

    # -- the one place that touches the bus --------------------------------

    async def _call(
        self,
        command: UserCommand,
        request: BaseModel,
        payload: Any,
        *,
        user_id: int | None = None,
        exclude_unset: bool = False,
    ) -> Any:
        """Send one command and return its payload, validated against ``payload``."""
        if self._rabbitmq is None:
            raise BusUnavailableError(Queue.USERS.value)

        message = {"command": command.value, "data": request.model_dump(mode="json", exclude_unset=exclude_unset)}

        try:
            raw = await self._rabbitmq.call(queue_name=Queue.USERS, message=message, timeout=self._timeout)
        except TimeoutError as exc:
            raise BusTimeoutError(command.value, self._timeout) from exc

        try:
            answer = TypeAdapter(RpcResponse[payload]).validate_python(raw)
        except ValidationError as exc:
            logger.error(f"Unreadable answer to {command.value}: {exc}")
            raise BusProtocolError(f"users service answered {command.value} off-contract") from exc

        if isinstance(answer, RpcError):
            self._raise_for(command, answer, user_id)

        return answer.data

    def _raise_for(self, command: UserCommand, answer: RpcError, user_id: int | None) -> None:
        """Turn a worker failure into the matching domain error.

        The worker's ``error`` text stops here, in the log. For conflicts the
        machine-readable half is ``error_type``, which names the colliding
        field -- branching on the prose ("already exists" in ...) is exactly
        the pattern this client exists to remove.
        """
        if answer.code is ErrorCode.NOT_FOUND:
            raise UserNotFoundError(user_id)

        if answer.code is ErrorCode.CONFLICT:
            if answer.error_type == "username":
                raise UsernameTakenError()
            raise EmailTakenError()

        if answer.code is ErrorCode.VALIDATION_ERROR:
            logger.error(f"users service rejected {command.value}: {answer.error}")
            raise BusProtocolError(f"users service rejected {command.value}")

        logger.error(f"users service failed {command.value}: {answer.error} [{answer.error_type}]")
        raise UpstreamFailureError(command.value)
