"""Typed access to the tasks service over the RPC bus.

Everything that knows the wire lives here: the queue, the command names, the
payload contracts and the envelope. A caller gets a validated contract back or
an exception -- never a dict to poke at with ``.get()``, and never an HTTP
status, which belongs to the layer above and is none of this layer's business.
"""

import logging
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from task_tracker_common.contracts.commands import (
    TaskAddTagContract,
    TaskCommand,
    TaskCreationContract,
    TaskDeleteContract,
    TaskGetByIdContract,
    TaskListContract,
    TaskRemoveTagContract,
    TaskStatsContract,
    TaskUpdateContract,
    TaskUpdatePayloadContract,
)
from task_tracker_common.contracts.queues import Queue
from task_tracker_common.contracts.responses import (
    ErrorCode,
    RpcError,
    RpcResponse,
    TaskData,
    TaskDelete,
    TaskList,
    TaskStats,
    TaskTags,
)

from ..config import RPC_TIMEOUT
from ..core.exceptions import (
    BusProtocolError,
    BusTimeoutError,
    BusUnavailableError,
    TaskNotFoundError,
    UpstreamFailureError,
)

logger = logging.getLogger(__name__)


class TasksBusClient:
    """The tasks service, as seen from the gateway."""

    def __init__(self, rabbitmq_client: Any, timeout: float = RPC_TIMEOUT) -> None:
        """Wrap a connected RabbitMQ client; ``None`` is allowed and answers BusUnavailableError."""
        self._rabbitmq = rabbitmq_client
        self._timeout = timeout

    # -- commands ---------------------------------------------------------

    async def create(self, task: TaskCreationContract) -> TaskData:
        """Create a task and return it as stored."""
        return await self._call(TaskCommand.CREATE, task, TaskData)

    async def get(self, task_id: int) -> TaskData:
        """Return one task with its tags, or raise TaskNotFoundError."""
        return await self._call(TaskCommand.GET, TaskGetByIdContract(id=task_id), TaskData, task_id=task_id)

    async def update(self, task_id: int, update: TaskUpdatePayloadContract) -> TaskData:
        """Apply a partial update and return the task as stored."""
        request = TaskUpdateContract(id=task_id, update=update)
        # The only call that excludes unset fields, and it has to: a partial
        # update is defined by which fields the caller named. Dumping the rest
        # at their defaults would blank every column the caller left alone.
        return await self._call(TaskCommand.UPDATE, request, TaskData, task_id=task_id, exclude_unset=True)

    async def delete(self, task_id: int) -> TaskDelete:
        """Delete a task, or raise TaskNotFoundError if it was not there."""
        return await self._call(TaskCommand.DELETE, TaskDeleteContract(id=task_id), TaskDelete, task_id=task_id)

    async def list_tasks(self, limit: int, offset: int) -> TaskList:
        """Return one page of tasks plus the count over the whole table."""
        return await self._call(TaskCommand.LIST, TaskListContract(limit=limit, offset=offset), TaskList)

    async def stats(self) -> TaskStats:
        """Return task counts per status, including the ``total`` key."""
        counts = await self._call(TaskCommand.STATS, TaskStatsContract(), TaskStats)
        # The payload is a mapping, so the contract cannot require this key on
        # its own -- the per-status keys come from the data, not the protocol.
        # Checking it here keeps the caller free of shape guesses.
        if "total" not in counts:
            raise BusProtocolError("task_stats answered without a total")
        return counts

    async def add_tag(self, task_id: int, tag_id: int) -> TaskTags:
        """Link a tag to a task and return the task's tags afterwards."""
        request = TaskAddTagContract(task_id=task_id, tag_id=tag_id)
        return await self._call(TaskCommand.ADD_TAG, request, TaskTags, task_id=task_id)

    async def remove_tag(self, task_id: int, tag_id: int) -> TaskTags:
        """Unlink a tag from a task and return the task's tags afterwards."""
        request = TaskRemoveTagContract(task_id=task_id, tag_id=tag_id)
        return await self._call(TaskCommand.REMOVE_TAG, request, TaskTags, task_id=task_id)

    # -- the one place that touches the bus --------------------------------

    async def _call(
        self,
        command: TaskCommand,
        request: BaseModel,
        payload: Any,
        *,
        task_id: int | None = None,
        exclude_unset: bool = False,
    ) -> Any:
        """Send one command and return its payload, validated against ``payload``.

        Dumping in JSON mode is not a detail: the transport is ``json.dumps``,
        which cannot serialise a ``date``. Handing it a contract dumped in
        python mode is how creating a task with a deadline used to answer 500.
        """
        if self._rabbitmq is None:
            raise BusUnavailableError(Queue.TASKS.value)

        message = {"command": command.value, "data": request.model_dump(mode="json", exclude_unset=exclude_unset)}

        try:
            raw = await self._rabbitmq.call(queue_name=Queue.TASKS, message=message, timeout=self._timeout)
        except TimeoutError as exc:
            raise BusTimeoutError(command.value, self._timeout) from exc

        try:
            answer = TypeAdapter(RpcResponse[payload]).validate_python(raw)
        except ValidationError as exc:
            # The worker answered something the protocol does not describe.
            # Treated as a protocol fault rather than a 500 with a traceback,
            # because the caller can do nothing about it either way.
            logger.error(f"Unreadable answer to {command.value}: {exc}")
            raise BusProtocolError(f"tasks service answered {command.value} off-contract") from exc

        if isinstance(answer, RpcError):
            self._raise_for(command, answer, task_id)

        return answer.data

    def _raise_for(self, command: TaskCommand, answer: RpcError, task_id: int | None) -> None:
        """Turn a worker failure into the matching domain error.

        This is the whole point of the ``code`` field. The worker's ``error``
        text stops here, in the log: it is written for whoever operates the
        system, and it used to travel all the way out to the HTTP client as a
        404 body carrying an asyncpg message.
        """
        if answer.code is ErrorCode.NOT_FOUND:
            raise TaskNotFoundError(task_id)

        if answer.code is ErrorCode.VALIDATION_ERROR:
            logger.error(f"tasks service rejected {command.value}: {answer.error}")
            raise BusProtocolError(f"tasks service rejected {command.value}")

        logger.error(f"tasks service failed {command.value}: {answer.error} [{answer.error_type}]")
        raise UpstreamFailureError(command.value)
