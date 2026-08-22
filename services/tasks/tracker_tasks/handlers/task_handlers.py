"""Task command handlers for RabbitMQ messages.

A handler receives a command contract that the dispatcher has already
validated, and answers with an envelope built from the shared response
contracts. Two things are therefore absent below and should stay absent: the
raw payload dict (``data.get("id")`` and its guards), and hand-written
``{"success": ...}`` literals.

Serialisation is absent too. Dates used to be walked field by field in every
handler; now the payload contract owns the shape and ``rpc_ok`` dumps it in
JSON mode, so a new date column is serialised by declaring it, not by
remembering to add a fifth ``isoformat()`` call in four places.
"""

import logging
from typing import Any

from task_tracker_common.contracts.commands import (
    TaskAddTagContract,
    TaskCreationContract,
    TaskDeleteContract,
    TaskGetByIdContract,
    TaskListContract,
    TaskRemoveTagContract,
    TaskStatsContract,
    TaskUpdateContract,
)
from task_tracker_common.contracts.responses import (
    ErrorCode,
    TaskData,
    TaskDelete,
    TaskList,
    TaskStats,
    TaskTags,
    rpc_error,
    rpc_ok,
)

from ..repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)

# The gateway turns this into the 404 body, so the wording is observable.
TASK_NOT_FOUND = "Task not found"

Envelope = dict[str, Any]


class TaskHandlers:
    """Handlers for task-related commands."""

    def __init__(self, repository: TaskRepository):
        """Initialize handlers with the repository they read and write through."""
        self.repository = repository

    async def handle_create_task(self, command: TaskCreationContract) -> Envelope:
        """Handle ``create_task``: insert the row, answer with the stored task."""
        task = await self.repository.create(command.model_dump())

        logger.info(f"Task created successfully: ID={task['id']}")
        # INSERT ... RETURNING cannot produce the tags aggregate, and a task
        # cannot have tags before it has an id, so the empty list is exact.
        return rpc_ok(TaskData, {**task, "tags": []})

    async def handle_get_task(self, command: TaskGetByIdContract) -> Envelope:
        """Handle ``get_task``: one row with its tags already aggregated by the query."""
        task = await self.repository.get_by_id(command.id)

        if task is None:
            logger.warning(f"Task not found: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, TASK_NOT_FOUND)

        logger.debug(f"Task retrieved: ID={command.id}")
        return rpc_ok(TaskData, task)

    async def handle_update_task(self, command: TaskUpdateContract) -> Envelope:
        """Handle ``update_task``: write the fields the caller actually set.

        ``exclude_unset`` is what makes this a partial update: a field the
        caller never mentioned is absent from the dump, so the repository's
        dynamic UPDATE leaves the column alone. Dumping without it would send
        every field at its default and blank the rest of the row.
        """
        update = command.update.model_dump(exclude_unset=True)

        if not update:
            return rpc_error(ErrorCode.VALIDATION_ERROR, "No fields to update")

        task = await self.repository.update(command.id, update)

        if task is None:
            logger.warning(f"Task not found for update: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, TASK_NOT_FOUND)

        # UPDATE ... RETURNING has no aggregate either: fetch the tags so the
        # answer has the same shape as get_task.
        tags = await self.repository.get_tags_for_task(command.id)

        logger.info(f"Task updated successfully: ID={command.id}")
        return rpc_ok(TaskData, {**task, "tags": tags})

    async def handle_delete_task(self, command: TaskDeleteContract) -> Envelope:
        """Handle ``delete_task``: report whether the row was there to delete."""
        deleted = await self.repository.delete(command.id)

        if not deleted:
            logger.warning(f"Task not found for deletion: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, TASK_NOT_FOUND)

        logger.info(f"Task deleted successfully: ID={command.id}")
        return rpc_ok(TaskDelete, {"id": command.id, "deleted": True})

    async def handle_list_tasks(self, command: TaskListContract) -> Envelope:
        """Handle ``list_tasks``: one page plus the count over the whole table.

        ``total`` is deliberately not ``len(tasks)``: the caller pages on it,
        and a page length would make the last page look like the whole set.
        """
        tasks = await self.repository.get_all(limit=command.limit, offset=command.offset)
        total = await self.repository.count_all()

        logger.debug(f"Listed {len(tasks)} tasks (total={total}, limit={command.limit}, offset={command.offset})")
        return rpc_ok(TaskList, {"tasks": tasks, "total": total})

    async def handle_task_stats(self, command: TaskStatsContract) -> Envelope:
        """Handle ``task_stats``: counts per status for the Kanban column totals.

        The command carries no fields -- the contract exists to say so, and to
        reject a payload that pretends otherwise.
        """
        counts = await self.repository.count_by_status()

        logger.debug(f"Task stats: {counts}")
        return rpc_ok(TaskStats, counts)

    async def handle_add_task_tag(self, command: TaskAddTagContract) -> Envelope:
        """Handle ``add_task_tag``: link an existing tag, answer with the task's tags."""
        if not await self.repository.get_by_id(command.task_id):
            logger.warning(f"Task not found for tagging: ID={command.task_id}")
            return rpc_error(ErrorCode.NOT_FOUND, TASK_NOT_FOUND)

        await self.repository.add_tag(command.task_id, command.tag_id)
        tags = await self.repository.get_tags_for_task(command.task_id)

        logger.info(f"Tag {command.tag_id} linked to task {command.task_id}")
        return rpc_ok(TaskTags, {"task_id": command.task_id, "tags": tags})

    async def handle_remove_task_tag(self, command: TaskRemoveTagContract) -> Envelope:
        """Handle ``remove_task_tag``: unlink a tag, answer with the task's tags."""
        await self.repository.remove_tag(command.task_id, command.tag_id)
        tags = await self.repository.get_tags_for_task(command.task_id)

        logger.info(f"Tag {command.tag_id} unlinked from task {command.task_id}")
        return rpc_ok(TaskTags, {"task_id": command.task_id, "tags": tags})
