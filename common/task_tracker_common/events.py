"""The event contract: what a task change looks like on the wire.

An event is an inter-service contract, the same way an RPC payload is: the
tasks worker builds one, the gateway's SSE leg consumes it, and neither side
gets to drift from the other. ``ts`` is set by the producer at build time --
the time of the fact, not the time of the delivery.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskEventType(StrEnum):
    CREATED = "task.created"
    UPDATED = "task.updated"
    DELETED = "task.deleted"


class TaskEvent(BaseModel):
    """One fact about one task.

    ``payload`` is deliberately not one shape: ``task.created`` and a
    renaming ``task.updated`` carry the full task snapshot under ``task``,
    while tag changes and deletion carry just ``{"id": N}`` -- the SSE board
    refetches on those, the same semantics the old Redis announcements had.
    Consumers must not assume more of ``payload`` than the type promises.
    """

    model_config = ConfigDict(extra="forbid")

    type: TaskEventType
    ts: str
    task_id: int
    payload: dict[str, Any]

    @classmethod
    def now(cls, type: TaskEventType, task_id: int, payload: dict[str, Any]) -> "TaskEvent":
        """Build an event stamped with the current moment."""
        return cls(
            type=type,
            ts=datetime.now(UTC).isoformat(),
            task_id=task_id,
            payload=payload,
        )

    def kafka_key(self) -> str:
        """The partition key: events of one task keep their order."""
        return str(self.task_id)
