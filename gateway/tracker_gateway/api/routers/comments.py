"""Comments router for Gateway API."""

import logging
from typing import Any

from fastapi import APIRouter

from ...core.config import RPC_TIMEOUT
from ..schemas.comment import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
)
from ._rpc import call_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comments", tags=["comments"])

QUEUE_NAME = "comments.commands"

# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


async def _call_comments(
    command: str, data: dict[str, Any], *, failure_status: int, failure_detail: str
) -> dict[str, Any]:
    """Send one comments command and return its payload, or raise the HTTP error."""
    return await call_worker(
        rabbitmq_client,
        queue=QUEUE_NAME,
        service="Comments",
        command=command,
        data=data,
        timeout=RPC_TIMEOUT,
        failure_status=failure_status,
        failure_detail=failure_detail,
    )


@router.post("", response_model=CommentResponse, status_code=201)
async def create_comment(comment: CommentCreate) -> CommentResponse:
    """Create a new comment."""
    data = await _call_comments(
        "create_comment",
        comment.model_dump(),
        failure_status=400,
        failure_detail="Unknown error",
    )
    logger.info(f"Comment created successfully: {data.get('id')}")
    return CommentResponse(**data)


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(comment_id: int) -> CommentResponse:
    """Get comment by ID."""
    data = await _call_comments(
        "get_comment",
        {"id": comment_id},
        failure_status=404,
        failure_detail="Comment not found",
    )
    return CommentResponse(**data)


@router.get("", response_model=CommentListResponse)
async def list_comments_by_task(task_id: int) -> CommentListResponse:
    """List comments for a task."""
    data = await _call_comments(
        "list_comments_by_task",
        {"task_id": task_id},
        failure_status=400,
        failure_detail="Unknown error",
    )
    comments = [CommentResponse(**c) for c in data["comments"]]
    return CommentListResponse(comments=comments, total=data.get("total", len(comments)))


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(comment_id: int, comment: CommentUpdate) -> CommentResponse:
    """Update comment by ID."""
    data = await _call_comments(
        "update_comment",
        {"id": comment_id, "update": comment.model_dump()},
        failure_status=404,
        failure_detail="Comment not found",
    )
    logger.info(f"Comment {comment_id} updated successfully")
    return CommentResponse(**data)


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(comment_id: int) -> None:
    """Delete comment by ID."""
    await _call_comments(
        "delete_comment",
        {"id": comment_id},
        failure_status=404,
        failure_detail="Comment not found",
    )
    logger.info(f"Comment {comment_id} deleted successfully")
