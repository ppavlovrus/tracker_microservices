"""Attachments router for Gateway API."""

import logging
from fastapi import APIRouter, HTTPException

from ...config import RPC_TIMEOUT
from ..schemas.attachment import (
    AttachmentCreate,
    AttachmentResponse,
    AttachmentListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])

QUEUE_NAME = "attachments.commands"

# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


@router.post("", response_model=AttachmentResponse, status_code=201)
async def create_attachment(attachment: AttachmentCreate) -> AttachmentResponse:
    """Register a new attachment."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "create_attachment", "data": attachment.model_dump()},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to create attachment: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        logger.info(f"Attachment created successfully: {response['data'].get('id')}")
        return AttachmentResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Attachments service response")
        raise HTTPException(status_code=504, detail="Attachments service timeout")
    except Exception as e:
        logger.error(f"Error creating attachment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(attachment_id: int) -> AttachmentResponse:
    """Get attachment by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "get_attachment", "data": {"id": attachment_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Attachment not found")
            logger.warning(f"Attachment {attachment_id} not found")
            raise HTTPException(status_code=404, detail=error_msg)

        return AttachmentResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Attachments service response")
        raise HTTPException(status_code=504, detail="Attachments service timeout")
    except Exception as e:
        logger.error(f"Error getting attachment {attachment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=AttachmentListResponse)
async def list_attachments_by_task(task_id: int) -> AttachmentListResponse:
    """List attachments for a task."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={
                "command": "list_attachments_by_task",
                "data": {"task_id": task_id},
            },
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to list attachments: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        data = response["data"]
        attachments = [AttachmentResponse(**a) for a in data["attachments"]]
        return AttachmentListResponse(
            attachments=attachments,
            total=data.get("total", len(attachments)),
        )

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Attachments service response")
        raise HTTPException(status_code=504, detail="Attachments service timeout")
    except Exception as e:
        logger.error(f"Error listing attachments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: int) -> None:
    """Delete attachment by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "delete_attachment", "data": {"id": attachment_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Attachment not found")
            logger.warning(f"Failed to delete attachment {attachment_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        logger.info(f"Attachment {attachment_id} deleted successfully")

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Attachments service response")
        raise HTTPException(status_code=504, detail="Attachments service timeout")
    except Exception as e:
        logger.error(f"Error deleting attachment {attachment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
