"""Tags router for Gateway API."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query

from ...core.config import CACHE_TTL_TAGS, RPC_TIMEOUT
from ..schemas.tags import (
    TagCreate,
    TagListResponse,
    TagResponse,
    TagUpdate,
)
from ._rpc import call_worker, require_bus

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


def _require_bus() -> None:
    """Refuse the request when there is nobody to ask."""
    require_bus(rabbitmq_client)


async def _call_tags(command: str, data: dict[str, Any], *, failure_status: int, failure_detail: str) -> dict[str, Any]:
    """Send one tags command and return its payload, or raise the HTTP error."""
    return await call_worker(
        rabbitmq_client,
        queue=QUEUE_NAME,
        service="Tags",
        command=command,
        data=data,
        timeout=RPC_TIMEOUT,
        failure_status=failure_status,
        failure_detail=failure_detail,
    )


async def _drop_cached_pages() -> None:
    """A tag write can land on any list page, so drop every cached one."""
    if cache:
        await cache.delete_pattern(TAGS_LIST_PATTERN)


async def _read_cached_page(limit: int, offset: int) -> TagListResponse | None:
    """Return a cached list page, or None on a miss or with no cache."""
    if not cache:
        return None
    cached = await cache.get_json(_tags_list_key(limit, offset))
    if cached is None:
        return None
    logger.debug(f"Cache HIT for tags list (limit={limit}, offset={offset})")
    return TagListResponse(**cached)


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag(tag: TagCreate) -> TagResponse:
    """Create a new tag."""
    data = await _call_tags("create_tag", tag.model_dump(), failure_status=400, failure_detail="Unknown error")
    await _drop_cached_pages()
    logger.info(f"Tag created successfully: {data.get('id')}")
    return TagResponse(**data)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: int) -> TagResponse:
    """Get tag by ID."""
    data = await _call_tags("get_tag", {"id": tag_id}, failure_status=404, failure_detail="Tag not found")
    return TagResponse(**data)


@router.get("", response_model=TagListResponse)
async def list_tags(
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TagListResponse:
    """List tags with pagination."""
    # Checked before the cache on purpose: with no bus this endpoint answers
    # 503 rather than serving a page that nothing can refresh.
    _require_bus()

    cached = await _read_cached_page(limit, offset)
    if cached is not None:
        return cached

    data = await _call_tags(
        "list_tags",
        {"limit": limit, "offset": offset},
        failure_status=400,
        failure_detail="Unknown error",
    )

    tags = [TagResponse(**t) for t in data["tags"]]
    result = TagListResponse(tags=tags, total=data.get("total", len(tags)), limit=limit, offset=offset)

    if cache:
        await cache.set_json(_tags_list_key(limit, offset), result.model_dump(mode="json"), CACHE_TTL_TAGS)

    return result


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: int, tag: TagUpdate) -> TagResponse:
    """Update tag by ID."""
    data = await _call_tags(
        "update_tag",
        {"id": tag_id, "update": tag.model_dump()},
        failure_status=404,
        failure_detail="Tag not found",
    )
    await _drop_cached_pages()
    logger.info(f"Tag {tag_id} updated successfully")
    return TagResponse(**data)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: int) -> None:
    """Delete tag by ID."""
    await _call_tags("delete_tag", {"id": tag_id}, failure_status=404, failure_detail="Tag not found")
    await _drop_cached_pages()
    logger.info(f"Tag {tag_id} deleted successfully")
