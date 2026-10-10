"""Comment command handlers for RabbitMQ messages.

A handler receives a command contract the dispatcher has already validated,
and answers with an envelope built from the shared response contracts. No
raw payload dicts, no hand-written ``{"success": ...}`` literals, and no
per-field date serialisation -- the response contract owns the shape and
``rpc_ok`` dumps it in JSON mode.
"""

import logging
from typing import Any

import asyncpg
from task_tracker_common.contracts.commands import (
    CommentCreationContract,
    CommentDeleteContract,
    CommentGetByIdContract,
    CommentListByTaskContract,
    CommentUpdateContract,
)
from task_tracker_common.contracts.responses import (
    CommentData,
    CommentDelete,
    CommentList,
    ErrorCode,
    rpc_error,
    rpc_ok,
)

from ..repositories.comment_repository import CommentRepository

logger = logging.getLogger(__name__)

# The gateway turns this into the 404 body, so the wording is observable.
COMMENT_NOT_FOUND = "Comment not found"

Envelope = dict[str, Any]


def _missing_reference(exc: asyncpg.ForeignKeyViolationError) -> Envelope:
    """Translate a foreign-key violation into an envelope naming the column.

    A comment pointed at a row that does not exist. The caller is the only one
    who can fix that, so it is reported as a missing reference rather than as
    an internal failure.
    """
    if exc.constraint_name == "comment_user_id_fkey":
        return rpc_error(ErrorCode.NOT_FOUND, "User not found", "user_id")
    return rpc_error(ErrorCode.NOT_FOUND, "Task not found", "task_id")


class CommentHandlers:
    """Handlers for comment-related commands."""

    def __init__(self, repository: CommentRepository):
        """Initialize handlers with the repository they read and write through."""
        self.repository = repository

    async def handle_create_comment(self, command: CommentCreationContract) -> Envelope:
        """Handle ``create_comment``: insert the row, answer with it as stored."""
        try:
            comment = await self.repository.create(command.model_dump())
        except asyncpg.ForeignKeyViolationError as e:
            logger.warning(f"Comment references a missing row: {e.constraint_name}")
            return _missing_reference(e)

        logger.info(f"Comment created successfully: ID={comment['id']}")
        return rpc_ok(CommentData, comment)

    async def handle_get_comment(self, command: CommentGetByIdContract) -> Envelope:
        """Handle ``get_comment``: one comment row by id."""
        comment = await self.repository.get_by_id(command.id)

        if comment is None:
            logger.warning(f"Comment not found: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, COMMENT_NOT_FOUND)

        return rpc_ok(CommentData, comment)

    async def handle_update_comment(self, command: CommentUpdateContract) -> Envelope:
        """Handle ``update_comment``: replace the content, touch ``updated_at``."""
        comment = await self.repository.update(command.id, command.update.model_dump())

        if comment is None:
            logger.warning(f"Comment not found for update: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, COMMENT_NOT_FOUND)

        logger.info(f"Comment updated successfully: ID={command.id}")
        return rpc_ok(CommentData, comment)

    async def handle_delete_comment(self, command: CommentDeleteContract) -> Envelope:
        """Handle ``delete_comment``: remove the row."""
        deleted = await self.repository.delete(command.id)

        if not deleted:
            logger.warning(f"Comment not found for deletion: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, COMMENT_NOT_FOUND)

        logger.info(f"Comment deleted successfully: ID={command.id}")
        return rpc_ok(CommentDelete, {"id": command.id, "deleted": True})

    async def handle_list_comments_by_task(self, command: CommentListByTaskContract) -> Envelope:
        """Handle ``list_comments_by_task``: one task's whole comment thread.

        Unpaginated on purpose: a thread is read whole, and the page bounds
        would live in the contract the day that stops being true.
        """
        comments = await self.repository.get_by_task_id(command.task_id)
        total = await self.repository.count_by_task_id(command.task_id)

        logger.debug(f"Listed {len(comments)} comments for task_id={command.task_id}")
        return rpc_ok(CommentList, {"comments": comments, "total": total})
