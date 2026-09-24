"""Attachments router for Gateway API."""

import logging
from typing import Any

from fastapi import APIRouter

from ...core.config import RPC_TIMEOUT
from ..schemas.attachment import (
    AttachmentCreate,
    AttachmentInitiateResponse,
    AttachmentListResponse,
    AttachmentResponse,
)
from ._rpc import call_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])

QUEUE_NAME = "attachments.commands"

# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


async def _call_attachments(
    command: str, data: dict[str, Any], *, failure_status: int, failure_detail: str
) -> dict[str, Any]:
    """Send one attachments command and return its payload, or raise the HTTP error."""
    return await call_worker(
        rabbitmq_client,
        queue=QUEUE_NAME,
        service="Attachments",
        command=command,
        data=data,
        timeout=RPC_TIMEOUT,
        failure_status=failure_status,
        failure_detail=failure_detail,
    )


@router.post("", response_model=AttachmentInitiateResponse, status_code=201)
async def create_attachment(attachment: AttachmentCreate) -> AttachmentInitiateResponse:
    """Initiate an attachment upload.

    Returns the attachment metadata plus a presigned URL the client uses to
    upload the file bytes directly to object storage.
    """
    data = await _call_attachments(
        "create_attachment",
        attachment.model_dump(),
        failure_status=400,
        failure_detail="Unknown error",
    )
    logger.info(f"Attachment created successfully: {data.get('id')}")
    return AttachmentInitiateResponse(**data)


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(attachment_id: int) -> AttachmentResponse:
    """Get attachment metadata with a presigned download URL."""
    data = await _call_attachments(
        "get_attachment",
        {"id": attachment_id},
        failure_status=404,
        failure_detail="Attachment not found",
    )
    return AttachmentResponse(**data)


@router.get("", response_model=AttachmentListResponse)
async def list_attachments_by_task(task_id: int) -> AttachmentListResponse:
    """List attachments for a task."""
    data = await _call_attachments(
        "list_attachments_by_task",
        {"task_id": task_id},
        failure_status=400,
        failure_detail="Unknown error",
    )
    attachments = [AttachmentResponse(**a) for a in data["attachments"]]
    return AttachmentListResponse(attachments=attachments, total=data.get("total", len(attachments)))


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: int) -> None:
    """Delete attachment by ID."""
    await _call_attachments(
        "delete_attachment",
        {"id": attachment_id},
        failure_status=404,
        failure_detail="Attachment not found",
    )
    logger.info(f"Attachment {attachment_id} deleted successfully")
