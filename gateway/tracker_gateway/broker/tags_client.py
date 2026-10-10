"""Typed access to the tags service over the RPC bus.

Everything that knows the wire lives here: the queue, the command names, the
payload contracts and the envelope. A caller gets a validated contract back or
an exception -- never a dict to poke at with ``.get()``, and never an HTTP
status, which belongs to the layer above and is none of this layer's business.
"""

import logging
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from task_tracker_common.contracts.commands import (
    TagCommand,
    TagCreationContract,
    TagDeleteContract,
    TagGetByIdContract,
    TagGetByNameContract,
    TagListContract,
    TagUpdateContract,
    TagUpdatePayloadContract,
)
from task_tracker_common.contracts.queues import Queue
from task_tracker_common.contracts.responses import (
    ErrorCode,
    RpcError,
    RpcResponse,
    TagData,
    TagDelete,
    TagList,
)

from ..core.config import RPC_TIMEOUT
from ..core.exceptions import (
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    TagNameTakenError,
    TagNotFoundError,
    UpstreamFailureError,
)

logger = logging.getLogger(__name__)


class TagsBusClient:
    """The tags service, as seen from the gateway."""

    def __init__(self, rabbitmq_client: Any, timeout: float = RPC_TIMEOUT) -> None:
        """Wrap a connected RabbitMQ client; ``None`` is allowed and answers BusUnavailableError."""
        self._rabbitmq = rabbitmq_client
        self._timeout = timeout

    # -- commands ---------------------------------------------------------

    async def create(self, tag: TagCreationContract) -> TagData:
        """Create a tag and return it as stored."""
        return await self._call(TagCommand.CREATE, tag, TagData)

    async def get(self, tag_id: int) -> TagData:
        """Return one tag, or raise TagNotFoundError."""
        return await self._call(TagCommand.GET, TagGetByIdContract(id=tag_id), TagData, tag_id=tag_id)

    async def get_by_name(self, name: str) -> TagData:
        """Return the tag with this name, or raise TagNotFoundError."""
        return await self._call(TagCommand.GET_BY_NAME, TagGetByNameContract(name=name), TagData)

    async def update(self, tag_id: int, name: str) -> TagData:
        """Rename a tag and return it as stored.

        Takes the name rather than a contract: a tag update is always exactly
        a rename, so there is no ``exclude_unset`` subtlety for the caller to
        keep alive the way a partial update has to.
        """
        request = TagUpdateContract(id=tag_id, update=TagUpdatePayloadContract(name=name))
        return await self._call(TagCommand.UPDATE, request, TagData, tag_id=tag_id)

    async def delete(self, tag_id: int) -> TagDelete:
        """Delete a tag, or raise TagNotFoundError if it was not there."""
        return await self._call(TagCommand.DELETE, TagDeleteContract(id=tag_id), TagDelete, tag_id=tag_id)

    async def list_tags(self, limit: int, offset: int) -> TagList:
        """Return one page of tags plus the count over the whole table."""
        return await self._call(TagCommand.LIST, TagListContract(limit=limit, offset=offset), TagList)

    # -- the one place that touches the bus --------------------------------

    async def _call(
        self,
        command: TagCommand,
        request: BaseModel,
        payload: Any,
        *,
        tag_id: int | None = None,
    ) -> Any:
        """Send one command and return its payload, validated against ``payload``."""
        if self._rabbitmq is None:
            raise BusUnavailableError(Queue.TAGS.value)

        message = {"command": command.value, "data": request.model_dump(mode="json")}

        try:
            raw = await self._rabbitmq.call(queue_name=Queue.TAGS, message=message, timeout=self._timeout)
        except TimeoutError as exc:
            raise BusTimeoutError(command.value, self._timeout) from exc

        try:
            answer = TypeAdapter(RpcResponse[payload]).validate_python(raw)
        except ValidationError as exc:
            logger.error(f"Unreadable answer to {command.value}: {exc}")
            raise BusProtocolError(f"tags service answered {command.value} off-contract") from exc

        if isinstance(answer, RpcError):
            self._raise_for(command, answer, tag_id)

        return answer.data

    def _raise_for(self, command: TagCommand, answer: RpcError, tag_id: int | None) -> None:
        """Turn a worker failure into the matching domain error.

        The worker's ``error`` text stops here, in the log. ``error_type``
        carries the machine-readable half -- the field that collided.
        """
        if answer.code is ErrorCode.NOT_FOUND:
            raise TagNotFoundError(tag_id)

        if answer.code is ErrorCode.CONFLICT:
            raise TagNameTakenError()

        if answer.code is ErrorCode.VALIDATION_ERROR:
            logger.error(f"tags service rejected {command.value}: {answer.error}")
            raise BusProtocolError(f"tags service rejected {command.value}")

        logger.error(f"tags service failed {command.value}: {answer.error} [{answer.error_type}]")
        raise UpstreamFailureError(command.value)
