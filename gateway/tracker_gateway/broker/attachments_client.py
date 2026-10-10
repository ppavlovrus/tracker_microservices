"""Typed access to the attachments service over the RPC bus.

Everything that knows the wire lives here: the queue, the command names, the
payload contracts and the envelope. A caller gets a validated contract back or
an exception -- never a dict to poke at with ``.get()``, and never an HTTP
status, which belongs to the layer above and is none of this layer's business.
"""

import logging
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from task_tracker_common.contracts.commands import (
    AttachmentCommand,
    AttachmentCreationContract,
    AttachmentDeleteContract,
    AttachmentGetByIdContract,
    AttachmentListByTaskContract,
)
from task_tracker_common.contracts.queues import Queue
from task_tracker_common.contracts.responses import (
    AttachmentData,
    AttachmentDelete,
    AttachmentInitiate,
    AttachmentList,
    ErrorCode,
    RpcError,
    RpcResponse,
)

from ..core.config import RPC_TIMEOUT
from ..core.exceptions import (
    AttachmentNotFoundError,
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    TaskNotFoundError,
    UpstreamFailureError,
)

logger = logging.getLogger(__name__)

# A NOT_FOUND answer is about the attachment itself unless the worker named a
# column instead: then the row that is missing is the task the request
# pointed at.
MISSING_REFERENCE = {
    "task_id": TaskNotFoundError,
}


class AttachmentsBusClient:
    """The attachments service, as seen from the gateway."""

    def __init__(self, rabbitmq_client: Any, timeout: float = RPC_TIMEOUT) -> None:
        """Wrap a connected RabbitMQ client; ``None`` is allowed and answers BusUnavailableError."""
        self._rabbitmq = rabbitmq_client
        self._timeout = timeout

    # -- commands ---------------------------------------------------------

    async def create(self, attachment: AttachmentCreationContract) -> AttachmentInitiate:
        """Record the metadata and return it with the presigned upload URL."""
        return await self._call(AttachmentCommand.CREATE, attachment, AttachmentInitiate)

    async def get(self, attachment_id: int) -> AttachmentData:
        """Return one attachment with a presigned download URL, or raise AttachmentNotFoundError."""
        return await self._call(
            AttachmentCommand.GET, AttachmentGetByIdContract(id=attachment_id), AttachmentData, attachment_id=attachment_id
        )

    async def delete(self, attachment_id: int) -> AttachmentDelete:
        """Delete an attachment, or raise AttachmentNotFoundError if it was not there."""
        return await self._call(
            AttachmentCommand.DELETE, AttachmentDeleteContract(id=attachment_id), AttachmentDelete, attachment_id=attachment_id
        )

    async def list_by_task(self, task_id: int) -> AttachmentList:
        """Return a task's attachments plus the count."""
        return await self._call(AttachmentCommand.LIST, AttachmentListByTaskContract(task_id=task_id), AttachmentList)

    # -- the one place that touches the bus --------------------------------

    async def _call(
        self,
        command: AttachmentCommand,
        request: BaseModel,
        payload: Any,
        *,
        attachment_id: int | None = None,
    ) -> Any:
        """Send one command and return its payload, validated against ``payload``."""
        if self._rabbitmq is None:
            raise BusUnavailableError(Queue.ATTACHMENTS.value)

        message = {"command": command.value, "data": request.model_dump(mode="json")}

        try:
            raw = await self._rabbitmq.call(queue_name=Queue.ATTACHMENTS, message=message, timeout=self._timeout)
        except TimeoutError as exc:
            raise BusTimeoutError(command.value, self._timeout) from exc

        try:
            answer = TypeAdapter(RpcResponse[payload]).validate_python(raw)
        except ValidationError as exc:
            logger.error(f"Unreadable answer to {command.value}: {exc}")
            raise BusProtocolError(f"attachments service answered {command.value} off-contract") from exc

        if isinstance(answer, RpcError):
            self._raise_for(command, answer, attachment_id)

        return answer.data

    def _raise_for(self, command: AttachmentCommand, answer: RpcError, attachment_id: int | None) -> None:
        """Turn a worker failure into the matching domain error.

        The worker's ``error`` text stops here, in the log. ``error_type``
        carries the machine-readable half -- the column that pointed nowhere.
        """
        if answer.code is ErrorCode.NOT_FOUND:
            missing = MISSING_REFERENCE.get(answer.error_type or "")
            if missing is not None:
                logger.info(f"attachments service refused {command.value}: {answer.error}")
                raise missing()
            raise AttachmentNotFoundError(attachment_id)

        if answer.code is ErrorCode.VALIDATION_ERROR:
            logger.error(f"attachments service rejected {command.value}: {answer.error}")
            raise BusProtocolError(f"attachments service rejected {command.value}")

        logger.error(f"attachments service failed {command.value}: {answer.error} [{answer.error_type}]")
        raise UpstreamFailureError(command.value)
