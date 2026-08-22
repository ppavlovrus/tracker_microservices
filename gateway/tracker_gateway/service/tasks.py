"""Task orchestration: the bus, the cache and the change notifications.

The router above this layer knows HTTP and nothing else; the client below it
knows the bus and nothing else. Everything in between lives here -- when a
cached copy may be served, which keys a write invalidates, and who gets told
that something changed.

It is written in bus contracts, not in the HTTP schemas from ``api/schemas``.
Importing those would point an inner layer at an outer one, and would make this
code unusable from the WebSocket and SSE endpoints, which have no request
models at all.
"""

import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from task_tracker_common.contracts.base import Contract
from task_tracker_common.contracts.commands import TaskCreationContract, TaskUpdatePayloadContract
from task_tracker_common.contracts.responses import TaskData, TaskList, TaskStats, TaskTag

from ..broker.tasks_client import TasksBusClient
from ..cache import Cache
from ..config import CACHE_TTL_TASK, CACHE_TTL_TASKS_LIST
from ..events import EventsHub

logger = logging.getLogger(__name__)

# Every cached list page, in one pattern. A write to any task can change any
# page, so pages are dropped wholesale rather than surgically.
LIST_PATTERN = "tasks:list:*"


def _task_key(task_id: int) -> str:
    """Cache key for a single task."""
    return f"task:{task_id}"


def _list_key(limit: int, offset: int) -> str:
    """Cache key for a tasks-list page."""
    return f"tasks:list:{limit}:{offset}"


class TaskService:
    """Everything the gateway does with tasks, minus the HTTP."""

    def __init__(self, bus: TasksBusClient, cache: Cache | None = None, events: EventsHub | None = None) -> None:
        """Take the collaborators; ``cache`` and ``events`` are optional by design."""
        self._bus = bus
        self._cache = cache
        self._events = events

    async def create(self, task: TaskCreationContract) -> TaskData:
        """Create a task, drop the cached pages it could appear on, announce it."""
        created = await self._bus.create(task)

        await self._drop_lists()
        await self._announce("task.created", {"task": created.model_dump(mode="json")})

        return created

    async def get(self, task_id: int) -> TaskData:
        """Return one task, from the cache when it is there."""
        cached = await self._cached(_task_key(task_id), TaskData)
        if cached is not None:
            logger.debug(f"Cache HIT for task {task_id}")
            return cached

        task = await self._bus.get(task_id)
        await self._store(_task_key(task_id), task, CACHE_TTL_TASK)

        logger.debug(f"Cache MISS for task {task_id}, served from RPC")
        return task

    async def list_tasks(self, limit: int, offset: int) -> TaskList:
        """Return one page of tasks, from the cache when it is there.

        Pages carry a short TTL as a backstop only: every write drops them, so
        the TTL matters just for the case where the write happened elsewhere.
        """
        key = _list_key(limit, offset)

        cached = await self._cached(key, TaskList)
        if cached is not None:
            logger.debug(f"Cache HIT for tasks list (limit={limit}, offset={offset})")
            return cached

        page = await self._bus.list_tasks(limit=limit, offset=offset)
        await self._store(key, page, CACHE_TTL_TASKS_LIST)

        logger.debug(f"Listed {len(page.tasks)} tasks (limit={limit}, offset={offset})")
        return page

    async def stats(self) -> TaskStats:
        """Return task counts per status.

        Not cached: it is a single-scan aggregate, and the Kanban column totals
        would be the first thing to look wrong if it lagged behind a write.
        """
        return await self._bus.stats()

    async def update(self, task_id: int, update: TaskUpdatePayloadContract) -> TaskData:
        """Apply a partial update, invalidate what it touched, announce it."""
        updated = await self._bus.update(task_id, update)

        await self._invalidate(task_id)
        await self._announce("task.updated", {"task": updated.model_dump(mode="json")})

        logger.info(f"Task {task_id} updated successfully")
        return updated

    async def delete(self, task_id: int) -> None:
        """Delete a task, invalidate what it touched, announce it."""
        await self._bus.delete(task_id)

        await self._invalidate(task_id)
        await self._announce("task.deleted", {"id": task_id})

        logger.info(f"Task {task_id} deleted successfully")

    async def add_tag(self, task_id: int, tag_id: int) -> list[TaskTag]:
        """Link a tag to a task and return the task's tags afterwards."""
        tags = await self._bus.add_tag(task_id, tag_id)

        await self._invalidate(task_id)
        await self._announce("task.updated", {"id": task_id})

        return tags.tags

    async def remove_tag(self, task_id: int, tag_id: int) -> list[TaskTag]:
        """Unlink a tag from a task and return the task's tags afterwards."""
        tags = await self._bus.remove_tag(task_id, tag_id)

        await self._invalidate(task_id)
        await self._announce("task.updated", {"id": task_id})

        return tags.tags

    # -- cache -------------------------------------------------------------

    async def _cached[T: Contract](self, key: str, contract: type[T]) -> T | None:
        """Read a cached value, or None when there is nothing usable there.

        A stored value that no longer satisfies its contract counts as a miss.
        Letting it raise instead would turn any change to a cached shape into a
        500 for every key written before the change, one per key, until the
        last of them expired.
        """
        if self._cache is None:
            return None

        raw = await self._cache.get_json(key)
        if raw is None:
            return None

        try:
            return contract.model_validate(raw)
        except ValidationError:
            logger.warning(f"Dropping cache entry {key}: no longer a valid {contract.__name__}")
            return None

    async def _store(self, key: str, value: Contract, ttl: int) -> None:
        """Cache a contract under ``key``, if there is a cache at all."""
        if self._cache is not None:
            await self._cache.set_json(key, value.model_dump(mode="json"), ttl)

    async def _drop_lists(self) -> None:
        """Drop every cached list page."""
        if self._cache is not None:
            await self._cache.delete_pattern(LIST_PATTERN)

    async def _invalidate(self, task_id: int) -> None:
        """Drop the cached task and every list page it could appear on."""
        if self._cache is not None:
            await self._cache.delete(_task_key(task_id))
            await self._cache.delete_pattern(LIST_PATTERN)

    # -- notifications -----------------------------------------------------

    async def _announce(self, event_type: str, payload: dict) -> None:
        """Best-effort SSE notification about a task change.

        Never raised into the caller: a failed notification must not fail the
        write it describes.
        """
        if self._events is None:
            return

        event = {"type": event_type, "ts": datetime.now(UTC).isoformat(), **payload}
        await self._events.publish(event)
