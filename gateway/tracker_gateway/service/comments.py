"""Comment orchestration.

The router above this layer knows HTTP and nothing else; the client below it
knows the bus and nothing else. Comments have no cache and no notifications,
so what is left here is a thin pass-through that exists for the shape of the
stack -- the seam where those concerns would land if the vertical ever grows
them, and the one place a caller would have to touch instead of every router.

It is written in bus contracts, not in the HTTP schemas from ``api/schemas``.
Importing those would point an inner layer at an outer one.
"""

import logging

from task_tracker_common.contracts.commands import CommentCreationContract
from task_tracker_common.contracts.responses import CommentData, CommentList

from ..broker.comments_client import CommentsBusClient

logger = logging.getLogger(__name__)


class CommentService:
    """Everything the gateway does with comments, minus the HTTP."""

    def __init__(self, bus: CommentsBusClient) -> None:
        """Take the collaborators."""
        self._bus = bus

    async def create(self, comment: CommentCreationContract) -> CommentData:
        """Create a comment and return it as stored."""
        return await self._bus.create(comment)

    async def get(self, comment_id: int) -> CommentData:
        """Return one comment, or raise CommentNotFoundError."""
        return await self._bus.get(comment_id)

    async def update(self, comment_id: int, content: str) -> CommentData:
        """Replace the content and return the comment as stored."""
        return await self._bus.update(comment_id, content)

    async def delete(self, comment_id: int) -> None:
        """Delete a comment."""
        await self._bus.delete(comment_id)

    async def list_by_task(self, task_id: int) -> CommentList:
        """Return a task's whole comment thread plus its count."""
        return await self._bus.list_by_task(task_id)
