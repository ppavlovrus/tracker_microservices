"""Tags router for Gateway API."""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Annotated

from ...config import RPC_TIMEOUT, CACHE_TTL_TAGS
from ..schemas.tags import (
    TagCreate,
    TagUpdate,
    TagResponse,
    TagListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tags", tags=["tags"])

QUEUE_NAME = "tags.commands"

# Pattern covering every cached tags-list page (keyed by limit/offset)
TAGS_LIST_PATTERN = "tags:list:*"

# Global RabbitMQ client (will be set in main.py lifespan)
rabbitmq_client = None

# Global cache instance (will be set in main.py lifespan)
cache = None


def set_rabbitmq_client(client):
    """Set RabbitMQ client instance."""
    global rabbitmq_client
    rabbitmq_client = client


def set_cache(c):
    """Set cache instance."""
    global cache
    cache = c


def _tags_list_key(limit: int, offset: int) -> str:
    """Cache key for a tags-list page."""
    return f"tags:list:{limit}:{offset}"


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag(tag: TagCreate) -> TagResponse:
    """Create a new tag."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "create_tag", "data": tag.model_dump()},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to create tag: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        # A new tag changes every list page -> drop all cached pages
        if cache:
            await cache.delete_pattern(TAGS_LIST_PATTERN)

        logger.info(f"Tag created successfully: {response['data'].get('id')}")
        return TagResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tags service response")
        raise HTTPException(status_code=504, detail="Tags service timeout")
    except Exception as e:
        logger.error(f"Error creating tag: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: int) -> TagResponse:
    """Get tag by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "get_tag", "data": {"id": tag_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Tag not found")
            logger.warning(f"Tag {tag_id} not found")
            raise HTTPException(status_code=404, detail=error_msg)

        return TagResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tags service response")
        raise HTTPException(status_code=504, detail="Tags service timeout")
    except Exception as e:
        logger.error(f"Error getting tag {tag_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=TagListResponse)
async def list_tags(
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TagListResponse:
    """List tags with pagination."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Cache-aside: try the cache first
    if cache:
        cached = await cache.get_json(_tags_list_key(limit, offset))
        if cached is not None:
            logger.debug(f"Cache HIT for tags list (limit={limit}, offset={offset})")
            return TagListResponse(**cached)

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={
                "command": "list_tags",
                "data": {"limit": limit, "offset": offset},
            },
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Failed to list tags: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        data = response["data"]
        tags = [TagResponse(**t) for t in data["tags"]]
        result = TagListResponse(
            tags=tags,
            total=data.get("total", len(tags)),
            limit=limit,
            offset=offset,
        )

        # Populate the cache for next time
        if cache:
            await cache.set_json(
                _tags_list_key(limit, offset),
                result.model_dump(mode="json"),
                CACHE_TTL_TAGS,
            )

        return result

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tags service response")
        raise HTTPException(status_code=504, detail="Tags service timeout")
    except Exception as e:
        logger.error(f"Error listing tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: int, tag: TagUpdate) -> TagResponse:
    """Update tag by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={
                "command": "update_tag",
                "data": {"id": tag_id, "update": tag.model_dump()},
            },
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Tag not found")
            logger.warning(f"Failed to update tag {tag_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        # Updated tag may appear on any list page -> drop all cached pages
        if cache:
            await cache.delete_pattern(TAGS_LIST_PATTERN)

        logger.info(f"Tag {tag_id} updated successfully")
        return TagResponse(**response["data"])

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tags service response")
        raise HTTPException(status_code=504, detail="Tags service timeout")
    except Exception as e:
        logger.error(f"Error updating tag {tag_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: int) -> None:
    """Delete tag by ID."""
    if not rabbitmq_client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        response = await rabbitmq_client.call(
            queue_name=QUEUE_NAME,
            message={"command": "delete_tag", "data": {"id": tag_id}},
            timeout=RPC_TIMEOUT,
        )

        if not response.get("success"):
            error_msg = response.get("error", "Tag not found")
            logger.warning(f"Failed to delete tag {tag_id}: {error_msg}")
            raise HTTPException(status_code=404, detail=error_msg)

        # Deleted tag changes every list page -> drop all cached pages
        if cache:
            await cache.delete_pattern(TAGS_LIST_PATTERN)

        logger.info(f"Tag {tag_id} deleted successfully")

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Timeout waiting for Tags service response")
        raise HTTPException(status_code=504, detail="Tags service timeout")
    except Exception as e:
        logger.error(f"Error deleting tag {tag_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
