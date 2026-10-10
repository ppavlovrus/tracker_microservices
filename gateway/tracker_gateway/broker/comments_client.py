"""Typed access to the comments service over the RPC bus.

Everything that knows the wire lives here: the queue, the command names, the
payload contracts and the envelope. A caller gets a validated contract back or
an exception -- never a dict to poke at with ``.get()``, and never an HTTP
status, which belongs to the layer above and is none of this layer's business.
"""

import logging
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from task_tracker_common.contracts.commands import (
    CommentCommand,
    CommentCreationContract,
    CommentDeleteContract,
    CommentGetByIdContract,
    CommentListByTaskContract,
    CommentUpdateContract,
    CommentUpdatePayloadContract,
)
from task_tracker_common.contracts.queues import Queue
from task_tracker_common.contracts.responses import (
    CommentData,
    CommentDelete,
    CommentList,
    ErrorCode,
    RpcError,
    RpcResponse,
)

from ..core.config import RPC_TIMEOUT
from ..core.exceptions import (
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    CommentNotFoundError,
    TaskNotFoundError,
    UpstreamFailureError,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)

# A NOT_FOUND answer is about the comment itself unless the worker named a
# column instead: then the row that is missing is one the request pointed at
# (a task that does not exist, an author nobody answers to).
MISSING_REFERENCE = {
    "task_id": TaskNotFoundError,
    "user_id": UserNotFoundError,
}


class CommentsBusClient:
    """The comments service, as seen from the gateway."""

    def __init__(self, rabbitmq_client: Any, timeout: float = RPC_TIMEOUT) -> None:
        """Wrap a connected RabbitMQ client; ``None`` is allowed and answers BusUnavailableError."""
        self._rabbitmq = rabbitmq_client
        self._timeout = timeout

    # -- commands ---------------------------------------------------------

    async def create(self, comment: CommentCreationContract) -> CommentData:
        """Create a comment and return it as stored."""
        return await self._call(CommentCommand.CREATE, comment, CommentData)

    async def get(self, comment_id: int) -> CommentData:
        """Return one comment, or raise CommentNotFoundError."""
        request = CommentGetByIdContract(id=comment_id)
        return await self._call(CommentCommand.GET, request, CommentData, comment_id=comment_id)

    async def update(self, comment_id: int, content: str) -> CommentData:
        """Replace the content and return the comment as stored.

        Takes the content rather than a contract: a comment update is always
        exactly a content replacement, so there is no ``exclude_unset``
        subtlety for the caller to keep alive the way a partial update has to.
        """
        request = CommentUpdateContract(id=comment_id, update=CommentUpdatePayloadContract(content=content))
        return await self._call(CommentCommand.UPDATE, request, CommentData, comment_id=comment_id)

    async def delete(self, comment_id: int) -> CommentDelete:
        """Delete a comment, or raise CommentNotFoundError if it was not there."""
        request = CommentDeleteContract(id=comment_id)
        return await self._call(CommentCommand.DELETE, request, CommentDelete, comment_id=comment_id)

    async def list_by_task(self, task_id: int) -> CommentList:
        """Return a task's whole comment thread plus its count."""
        return await self._call(CommentCommand.LIST, CommentListByTaskContract(task_id=task_id), CommentList)

    # -- the one place that touches the bus --------------------------------

    async def _call(
        self,
        command: CommentCommand,
        request: BaseModel,
        payload: Any,
        *,
        comment_id: int | None = None,
    ) -> Any:
        """Send one command and return its payload, validated against ``payload``."""
        if self._rabbitmq is None:
            raise BusUnavailableError(Queue.COMMENTS.value)

        message = {"command": command.value, "data": request.model_dump(mode="json")}

        try:
            raw = await self._rabbitmq.call(queue_name=Queue.COMMENTS, message=message, timeout=self._timeout)
        except TimeoutError as exc:
            raise BusTimeoutError(command.value, self._timeout) from exc

        try:
            answer = TypeAdapter(RpcResponse[payload]).validate_python(raw)
        except ValidationError as exc:
            logger.error(f"Unreadable answer to {command.value}: {exc}")
            raise BusProtocolError(f"comments service answered {command.value} off-contract") from exc

        if isinstance(answer, RpcError):
            self._raise_for(command, answer, comment_id)

        return answer.data

    def _raise_for(self, command: CommentCommand, answer: RpcError, comment_id: int | None) -> None:
        """Turn a worker failure into the matching domain error.

        The worker's ``error`` text stops here, in the log. ``error_type``
        carries the machine-readable half -- the column that pointed nowhere.
        """
        if answer.code is ErrorCode.NOT_FOUND:
            missing = MISSING_REFERENCE.get(answer.error_type or "")
            if missing is not None:
                logger.info(f"comments service refused {command.value}: {answer.error}")
                raise missing()
            raise CommentNotFoundError(comment_id)

        if answer.code is ErrorCode.VALIDATION_ERROR:
            logger.error(f"comments service rejected {command.value}: {answer.error}")
            raise BusProtocolError(f"comments service rejected {command.value}")

        logger.error(f"comments service failed {command.value}: {answer.error} [{answer.error_type}]")
        raise UpstreamFailureError(command.value)
