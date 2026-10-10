"""Attachments router for Gateway API.

Every endpoint does the same three things and nothing else: turn the request
into a bus contract, hand it to the service, and shape the answer for HTTP.
No try/except, no HTTPException -- failures come back as domain exceptions
and ``api/errors.py`` is the only place they become statuses.

The file bytes never cross this gateway: the create answer carries a
presigned upload URL and the single-item answer a presigned download URL, and
the client talks to object storage directly.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from task_tracker_common.contracts.base import INT4_MAX
from task_tracker_common.contracts.commands import AttachmentCreationContract

from ..deps import AttachmentsServiceDep
from ..schemas.attachment import (
    AttachmentCreate,
    AttachmentInitiateResponse,
    AttachmentListResponse,
    AttachmentResponse,
)

# Path ids are bounded to the width of the column they address. The bound is
# not decoration: the payload contracts require a positive int4, and a
# contract that fails to build inside the bus client would surface as a bare
# 500. The edge must be at least as strict as the contract behind it.
AttachmentId = Annotated[int, Path(ge=1, le=INT4_MAX)]
TaskIdQuery = Annotated[int, Query(ge=1, le=INT4_MAX)]

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentInitiateResponse, status_code=201)
async def create_attachment(attachment: AttachmentCreate, service: AttachmentsServiceDep) -> AttachmentInitiateResponse:
    """Initiate an attachment upload: metadata plus a presigned PUT URL."""
    initiated = await service.create(AttachmentCreationContract(**attachment.model_dump()))
    return AttachmentInitiateResponse(**initiated.model_dump())


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(attachment_id: AttachmentId, service: AttachmentsServiceDep) -> AttachmentResponse:
    """Get attachment metadata with a presigned download URL."""
    attachment = await service.get(attachment_id)
    return AttachmentResponse(**attachment.model_dump())


@router.get("", response_model=AttachmentListResponse)
async def list_attachments_by_task(task_id: TaskIdQuery, service: AttachmentsServiceDep) -> AttachmentListResponse:
    """List every attachment of one task."""
    page = await service.list_by_task(task_id)

    return AttachmentListResponse(
        attachments=[AttachmentResponse(**attachment.model_dump()) for attachment in page.attachments],
        total=page.total,
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(attachment_id: AttachmentId, service: AttachmentsServiceDep) -> None:
    """Delete attachment by ID."""
    await service.delete(attachment_id)
