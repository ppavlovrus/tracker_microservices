"""Tags router for Gateway API.

Every endpoint does the same three things and nothing else: turn the request
into a bus contract, hand it to the service, and shape the answer for HTTP.
No try/except, no HTTPException -- failures come back as domain exceptions
and ``api/errors.py`` is the only place they become statuses.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query
from task_tracker_common.contracts.base import INT4_MAX
from task_tracker_common.contracts.commands import TagCreationContract

from ..deps import TagsServiceDep
from ..schemas.tags import (
    TagCreate,
    TagListResponse,
    TagResponse,
    TagUpdate,
)

# Path ids are bounded to the width of the column they address. The bound is
# not decoration: the payload contracts require a positive int4, and a
# contract that fails to build inside the bus client would surface as a bare
# 500. The edge must be at least as strict as the contract behind it.
TagId = Annotated[int, Path(ge=1, le=INT4_MAX)]

router = APIRouter(prefix="/tags", tags=["tags"])


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag(tag: TagCreate, service: TagsServiceDep) -> TagResponse:
    """Create a new tag."""
    created = await service.create(TagCreationContract(**tag.model_dump()))
    return TagResponse(**created.model_dump())


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: TagId, service: TagsServiceDep) -> TagResponse:
    """Get tag by ID."""
    tag = await service.get(tag_id)
    return TagResponse(**tag.model_dump())


@router.get("", response_model=TagListResponse)
async def list_tags(
    service: TagsServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TagListResponse:
    """List tags with pagination."""
    page = await service.list_tags(limit=limit, offset=offset)

    # `limit` and `offset` are the caller's own request echoed back; the page
    # itself does not carry them, because the bus contract describes the data.
    return TagListResponse(
        tags=[TagResponse(**tag.model_dump()) for tag in page.tags],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: TagId, tag: TagUpdate, service: TagsServiceDep) -> TagResponse:
    """Update tag by ID."""
    updated = await service.update(tag_id, tag.name)
    return TagResponse(**updated.model_dump())


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: TagId, service: TagsServiceDep) -> None:
    """Delete tag by ID."""
    await service.delete(tag_id)
