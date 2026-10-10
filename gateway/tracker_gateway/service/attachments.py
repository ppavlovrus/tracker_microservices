"""Attachment orchestration.

The router above this layer knows HTTP and nothing else; the client below it
knows the bus and nothing else. Attachments have no cache and no
notifications, so what is left here is a thin pass-through that exists for the
shape of the stack -- the seam where those concerns would land if the vertical
ever grows them, and the one place a caller would have to touch instead of
every router.

It is written in bus contracts, not in the HTTP schemas from ``api/schemas``.
Importing those would point an inner layer at an outer one.
"""

import logging

from task_tracker_common.contracts.commands import AttachmentCreationContract
from task_tracker_common.contracts.responses import AttachmentData, AttachmentInitiate, AttachmentList

from ..broker.attachments_client import AttachmentsBusClient

logger = logging.getLogger(__name__)


class AttachmentService:
    """Everything the gateway does with attachments, minus the HTTP."""

    def __init__(self, bus: AttachmentsBusClient) -> None:
        """Take the collaborators."""
        self._bus = bus

    async def create(self, attachment: AttachmentCreationContract) -> AttachmentInitiate:
        """Record the metadata and return it with the presigned upload URL."""
        return await self._bus.create(attachment)

    async def get(self, attachment_id: int) -> AttachmentData:
        """Return one attachment with a presigned download URL."""
        return await self._bus.get(attachment_id)

    async def delete(self, attachment_id: int) -> None:
        """Delete an attachment (the object first, then the row)."""
        await self._bus.delete(attachment_id)

    async def list_by_task(self, task_id: int) -> AttachmentList:
        """Return a task's attachments plus the count."""
        return await self._bus.list_by_task(task_id)
