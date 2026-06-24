"""Comments router for Gateway API."""

import logging
from fastapi import APIRouter, HTTPException

from ...config import RPC_TIMEOUT
from ..schemas.comment import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comments", tags=["comments"])

QUEUE_NAME = "comments.commands"

# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


@router.post("", response_model=CommentResponse, status_code=201)
async def create_comment(comment: CommentCreate) -> CommentResponse:
    """Create a new comment."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "create_comment", "data": comment.model_dump()},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to create comment: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        logger.info(f"Comment created successfully: {response['data'].get('id')}")
        return CommentResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Comments service response")
        raise HTTPException(status_code=504, detail="Comments service timeout")
    except Exception as e:
        logger.error(f"Error creating comment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(comment_id: int) -> CommentResponse:
    """Get comment by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "get_comment", "data": {"id": comment_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Comment not found")
            logger.warning(f"Comment {comment_id} not found")
            raise HTTPException(status_code=404, detail=error_msg)

        return CommentResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Comments service response")
        raise HTTPException(status_code=504, detail="Comments service timeout")
    except Exception as e:
        logger.error(f"Error getting comment {comment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=CommentListResponse)
async def list_comments_by_task(task_id: int) -> CommentListResponse:
    """List comments for a task."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "list_comments_by_task", "data": {"task_id": task_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to list comments: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        data = response["data"]
        comments = [CommentResponse(**c) for c in data["comments"]]
        return CommentListResponse(comments=comments, total=data.get("total", len(comments)))

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Comments service response")
        raise HTTPException(status_code=504, detail="Comments service timeout")
    except Exception as e:
        logger.error(f"Error listing comments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(comment_id: int, comment: CommentUpdate) -> CommentResponse:
    """Update comment by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={
                "command": "update_comment",
                "data": {"id": comment_id, "update": comment.model_dump()},
            },
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Comment not found")
            logger.warning(f"Failed to update comment {comment_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        logger.info(f"Comment {comment_id} updated successfully")
        return CommentResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Comments service response")
        raise HTTPException(status_code=504, detail="Comments service timeout")
    except Exception as e:
        logger.error(f"Error updating comment {comment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(comment_id: int) -> None:
    """Delete comment by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "delete_comment", "data": {"id": comment_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Comment not found")
            logger.warning(f"Failed to delete comment {comment_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        logger.info(f"Comment {comment_id} deleted successfully")

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Comments service response")
        raise HTTPException(status_code=504, detail="Comments service timeout")
    except Exception as e:
        logger.error(f"Error deleting comment {comment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
