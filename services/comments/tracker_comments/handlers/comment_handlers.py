"""Comment command handlers for RabbitMQ messages."""

import logging
from typing import Any

import asyncpg
from task_tracker_common.contracts.responses import ErrorCode, rpc_error

from ..repositories.comment_repository import CommentRepository

logger = logging.getLogger(__name__)


def _internal(exc: Exception) -> dict[str, Any]:
    """The answer to an exception nobody classified.

    ``str(exc)`` belongs in the log and stays there. It used to be the HTTP
    body as well, which is how a foreign-key violation reached clients
    carrying the table, the constraint name and the offending value.
    """
    return rpc_error(ErrorCode.INTERNAL, "Internal error", type(exc).__name__)


def _missing_reference(exc: asyncpg.ForeignKeyViolationError) -> dict[str, Any]:
    """Translate a foreign-key violation into an envelope naming the column.

    A comment pointed at a row that does not exist. The caller is the only one
    who can fix that, so it is reported as a missing reference rather than as
    an internal failure.
    """
    if exc.constraint_name == "comment_user_id_fkey":
        return rpc_error(ErrorCode.NOT_FOUND, "User not found", "user_id")
    return rpc_error(ErrorCode.NOT_FOUND, "Task not found", "task_id")

# Columns that come back from asyncpg as datetimes. The transport is
# json.dumps, which cannot serialise one, so every handler that returns a
# comment has to convert them -- once, here, instead of four times below.
TIMESTAMP_FIELDS = ("created_at", "updated_at")


def _serialize_timestamps(comment: dict[str, Any]) -> dict[str, Any]:
    """Replace the datetime columns of one comment with ISO strings."""
    for field in TIMESTAMP_FIELDS:
        if comment.get(field):
            comment[field] = comment[field].isoformat()
    return comment


class CommentHandlers:
    """Handlers for comment-related commands."""

    def __init__(self, repository: CommentRepository):
        """
        Initialize handlers.

        Args:
            repository: CommentRepository instance
        """
        self.repository = repository

    async def handle_create_comment(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle create_comment command.

        Args:
            data: Comment data from command

        Returns:
            Response with created comment or error
        """
        try:
            # Validate required fields
            if not data.get("task_id"):
                return {"success": False, "error": "Task ID is required"}

            if not data.get("user_id"):
                return {"success": False, "error": "User ID is required"}

            if not data.get("content"):
                return {"success": False, "error": "Content is required"}

            # Create comment
            comment = await self.repository.create(data)

            _serialize_timestamps(comment)

            logger.info(f"Comment created successfully: ID={comment['id']}")

            return {"success": True, "data": comment}

        except asyncpg.ForeignKeyViolationError as e:
            logger.warning(f"Comment references a missing row: {e.constraint_name}")
            return _missing_reference(e)

        except Exception as e:
            logger.error(f"Error creating comment: {e}", exc_info=True)
            return _internal(e)

    async def handle_get_comment(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle get_comment command.

        Args:
            data: Contains comment ID

        Returns:
            Response with comment data or error
        """
        try:
            comment_id = data.get("id")

            if not comment_id:
                return {"success": False, "error": "Comment ID is required"}

            comment = await self.repository.get_by_id(comment_id)

            if not comment:
                return {"success": False, "error": "Comment not found"}

            _serialize_timestamps(comment)

            logger.debug(f"Comment retrieved: ID={comment_id}")

            return {"success": True, "data": comment}

        except Exception as e:
            logger.error(f"Error getting comment: {e}", exc_info=True)
            return _internal(e)

    async def handle_update_comment(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle update_comment command.

        Args:
            data: Contains comment ID and update fields

        Returns:
            Response with updated comment or error
        """
        try:
            comment_id = data.get("id")
            update_data = data.get("update", {})

            if not comment_id:
                return {"success": False, "error": "Comment ID is required"}

            if not update_data or not update_data.get("content"):
                return {"success": False, "error": "Content is required for update"}

            # Update comment
            comment = await self.repository.update(comment_id, update_data)

            if not comment:
                return {"success": False, "error": "Comment not found"}

            _serialize_timestamps(comment)

            logger.info(f"Comment updated successfully: ID={comment_id}")

            return {"success": True, "data": comment}

        except Exception as e:
            logger.error(f"Error updating comment: {e}", exc_info=True)
            return _internal(e)

    async def handle_delete_comment(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle delete_comment command.

        Args:
            data: Contains comment ID

        Returns:
            Response indicating success or error
        """
        try:
            comment_id = data.get("id")

            if not comment_id:
                return {"success": False, "error": "Comment ID is required"}

            deleted = await self.repository.delete(comment_id)

            if not deleted:
                return {"success": False, "error": "Comment not found"}

            logger.info(f"Comment deleted successfully: ID={comment_id}")

            return {"success": True, "data": {"deleted": True, "id": comment_id}}

        except Exception as e:
            logger.error(f"Error deleting comment: {e}", exc_info=True)
            return _internal(e)

    async def handle_list_comments_by_task(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle list_comments_by_task command.

        Args:
            data: Contains task_id

        Returns:
            Response with list of comments or error
        """
        try:
            task_id = data.get("task_id")

            if not task_id:
                return {"success": False, "error": "Task ID is required"}

            # Get comments and total count for task
            comments = await self.repository.get_by_task_id(task_id)
            total = await self.repository.count_by_task_id(task_id)

            for comment in comments:
                _serialize_timestamps(comment)

            logger.debug(f"Listed {len(comments)} comments for task_id={task_id}")

            return {"success": True, "data": {"comments": comments, "total": total}}

        except Exception as e:
            logger.error(f"Error listing comments: {e}", exc_info=True)
            return _internal(e)
