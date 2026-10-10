"""Comments router for Gateway API.

Every endpoint does the same three things and nothing else: turn the request
into a bus contract, hand it to the service, and shape the answer for HTTP.
No try/except, no HTTPException -- failures come back as domain exceptions
and ``api/errors.py`` is the only place they become statuses.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from task_tracker_common.contracts.base import INT4_MAX
from task_tracker_common.contracts.commands import CommentCreationContract

from ..deps import CommentsServiceDep
from ..schemas.comment import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
)

# Path ids are bounded to the width of the column they address. The bound is
# not decoration: the payload contracts require a positive int4, and a
# contract that fails to build inside the bus client would surface as a bare
# 500. The edge must be at least as strict as the contract behind it.
CommentId = Annotated[int, Path(ge=1, le=INT4_MAX)]
TaskIdQuery = Annotated[int, Query(ge=1, le=INT4_MAX)]

router = APIRouter(prefix="/comments", tags=["comments"])


@router.post("", response_model=CommentResponse, status_code=201)
async def create_comment(comment: CommentCreate, service: CommentsServiceDep) -> CommentResponse:
    """Create a new comment."""
    created = await service.create(CommentCreationContract(**comment.model_dump()))
    return CommentResponse(**created.model_dump())


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(comment_id: CommentId, service: CommentsServiceDep) -> CommentResponse:
    """Get comment by ID."""
    comment = await service.get(comment_id)
    return CommentResponse(**comment.model_dump())


@router.get("", response_model=CommentListResponse)
async def list_comments_by_task(task_id: TaskIdQuery, service: CommentsServiceDep) -> CommentListResponse:
    """List every comment of one task."""
    thread = await service.list_by_task(task_id)

    return CommentListResponse(
        comments=[CommentResponse(**comment.model_dump()) for comment in thread.comments],
        total=thread.total,
    )


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(comment_id: CommentId, comment: CommentUpdate, service: CommentsServiceDep) -> CommentResponse:
    """Update comment by ID."""
    updated = await service.update(comment_id, comment.content)
    return CommentResponse(**updated.model_dump())


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(comment_id: CommentId, service: CommentsServiceDep) -> None:
    """Delete comment by ID."""
    await service.delete(comment_id)
