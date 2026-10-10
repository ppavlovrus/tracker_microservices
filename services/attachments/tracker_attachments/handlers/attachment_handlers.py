"""Attachment command handlers for RabbitMQ messages.

A handler receives a command contract the dispatcher has already validated,
and answers with an envelope built from the shared response contracts. No
raw payload dicts, no hand-written ``{"success": ...}`` literals, and no
timestamp juggling -- the response contract owns the shape and ``rpc_ok``
dumps it in JSON mode.

The bytes never travel the bus: the client uploads and downloads them
directly against object storage, over the presigned URLs built here. This
service only owns the metadata row and the object lifecycle.
"""

import logging
from typing import Any

import asyncpg
from task_tracker_common.contracts.commands import (
    AttachmentCreationContract,
    AttachmentDeleteContract,
    AttachmentGetByIdContract,
    AttachmentListByTaskContract,
)
from task_tracker_common.contracts.responses import (
    AttachmentData,
    AttachmentDelete,
    AttachmentInitiate,
    AttachmentList,
    ErrorCode,
    rpc_error,
    rpc_ok,
)

from ..repositories.attachment_repository import AttachmentRepository
from ..storage import S3Storage, build_object_key

logger = logging.getLogger(__name__)

# The gateway turns this into the 404 body, so the wording is observable.
ATTACHMENT_NOT_FOUND = "Attachment not found"

Envelope = dict[str, Any]


def _missing_reference(exc: asyncpg.ForeignKeyViolationError) -> Envelope:
    """Translate a foreign-key violation into a missing-reference envelope.

    ``attachment_task_id_fkey`` is the only foreign key on the table, so a
    violation is always about the task; ``error_type`` still names the column,
    the machine-readable half the gateway picks its domain error from.
    """
    logger.warning(f"Attachment references a missing row: {exc.constraint_name}")
    return rpc_error(ErrorCode.NOT_FOUND, "Task not found", "task_id")


class AttachmentHandlers:
    """Handlers for attachment-related commands."""

    def __init__(self, repository: AttachmentRepository, storage: S3Storage):
        """Initialize handlers with the repository and the object storage port."""
        self.repository = repository
        self.storage = storage

    async def handle_create_attachment(self, command: AttachmentCreationContract) -> Envelope:
        """Handle ``create_attachment``: record the metadata, presign the upload.

        The storage key is generated server-side, never supplied by the client,
        so every object lands under its task's namespace.
        """
        try:
            key = build_object_key(command.task_id, command.filename)
            attachment = await self.repository.create(command.model_dump() | {"storage_path": key})
        except asyncpg.ForeignKeyViolationError as e:
            return _missing_reference(e)

        attachment |= {
            "upload_url": self.storage.presigned_put_url(key),
            "upload_expires_in": self.storage.presign_expire,
        }

        logger.info(f"Attachment initiated successfully: ID={attachment['id']}")
        return rpc_ok(AttachmentInitiate, attachment)

    async def handle_get_attachment(self, command: AttachmentGetByIdContract) -> Envelope:
        """Handle ``get_attachment``: one metadata row plus a presigned download."""
        attachment = await self.repository.get_by_id(command.id)

        if attachment is None:
            logger.warning(f"Attachment not found: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, ATTACHMENT_NOT_FOUND)

        attachment["download_url"] = self.storage.presigned_get_url(attachment["storage_path"])

        return rpc_ok(AttachmentData, attachment)

    async def handle_delete_attachment(self, command: AttachmentDeleteContract) -> Envelope:
        """Handle ``delete_attachment``: remove the object, then the row.

        Two steps on two systems, so they cannot be atomic. The object goes
        first: the other order can leak a row pointing at nothing, while this
        one can at worst leave an unreferenced object -- recoverable, and
        invisible to the application.
        """
        attachment = await self.repository.get_by_id(command.id)

        if attachment is None:
            logger.warning(f"Attachment not found for deletion: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, ATTACHMENT_NOT_FOUND)

        await self.storage.delete(attachment["storage_path"])
        await self.repository.delete(command.id)

        logger.info(f"Attachment deleted successfully: ID={command.id}")
        return rpc_ok(AttachmentDelete, {"id": command.id, "deleted": True})

    async def handle_list_attachments_by_task(self, command: AttachmentListByTaskContract) -> Envelope:
        """Handle ``list_attachments_by_task``: every attachment of one task.

        Unpaginated on purpose: a task's file list is read whole, and the page
        bounds would live in the contract the day that stops being true.
        """
        attachments = await self.repository.get_by_task_id(command.task_id)
        total = await self.repository.count_by_task_id(command.task_id)

        logger.debug(f"Listed {len(attachments)} attachments for task_id={command.task_id}")
        return rpc_ok(AttachmentList, {"attachments": attachments, "total": total})
