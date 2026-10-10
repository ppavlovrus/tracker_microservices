"""Tag orchestration: the bus and the cached list pages.

The router above this layer knows HTTP and nothing else; the client below it
knows the bus and nothing else. What lives in between is the one decision this
vertical has: which list pages are cached, and which writes drop them.

It is written in bus contracts, not in the HTTP schemas from ``api/schemas``.
Importing those would point an inner layer at an outer one.
"""

import logging

from pydantic import ValidationError
from task_tracker_common.contracts.base import Contract
from task_tracker_common.contracts.commands import TagCreationContract
from task_tracker_common.contracts.responses import TagData, TagList

from ..broker.tags_client import TagsBusClient
from ..core.config import CACHE_TTL_TAGS
from ..storage.cache import Cache

logger = logging.getLogger(__name__)

# Every cached list page, in one pattern. A write can land a tag on any page,
# so pages are dropped wholesale rather than surgically.
LIST_PATTERN = "tags:list:*"


def _list_key(limit: int, offset: int) -> str:
    """Cache key for a tags-list page."""
    return f"tags:list:{limit}:{offset}"


class TagService:
    """Everything the gateway does with tags, minus the HTTP."""

    def __init__(self, bus: TagsBusClient, cache: Cache | None = None) -> None:
        """Take the collaborators; the cache is optional by design."""
        self._bus = bus
        self._cache = cache

    async def create(self, tag: TagCreationContract) -> TagData:
        """Create a tag and drop the list pages it could appear on."""
        created = await self._bus.create(tag)
        await self._drop_lists()
        return created

    async def get(self, tag_id: int) -> TagData:
        """Return one tag. Individual tags are not cached -- only pages are."""
        return await self._bus.get(tag_id)

    async def get_by_name(self, name: str) -> TagData:
        """Return the tag with this name, or raise TagNotFoundError."""
        return await self._bus.get_by_name(name)

    async def update(self, tag_id: int, name: str) -> TagData:
        """Rename a tag and drop the list pages it appears on."""
        updated = await self._bus.update(tag_id, name)
        await self._drop_lists()
        return updated

    async def delete(self, tag_id: int) -> None:
        """Delete a tag and drop the list pages it appeared on."""
        await self._bus.delete(tag_id)
        await self._drop_lists()

    async def list_tags(self, limit: int, offset: int) -> TagList:
        """Return one page of tags, from the cache when it is there.

        The cache is read before the bus, so with the bus down a warm page is
        still served until its TTL runs out -- the same graceful degradation
        the tasks list has. A cold read has nobody to ask and answers 503.
        """
        key = _list_key(limit, offset)

        cached = await self._cached(key, TagList)
        if cached is not None:
            logger.debug(f"Cache HIT for tags list (limit={limit}, offset={offset})")
            return cached

        page = await self._bus.list_tags(limit=limit, offset=offset)
        await self._store(key, page, CACHE_TTL_TAGS)
        return page

    # -- cache -------------------------------------------------------------

    async def _cached[T: Contract](self, key: str, contract: type[T]) -> T | None:
        """Read a cached value, or None when there is nothing usable there.

        A stored value that no longer satisfies its contract counts as a miss.
        Letting it raise instead would turn any change to a cached shape into a
        500 for every key written before the change, one per key, until the
        last of them expired.
        """
        if self._cache is None:
            return None

        raw = await self._cache.get_json(key)
        if raw is None:
            return None

        try:
            return contract.model_validate(raw)
        except ValidationError:
            logger.warning(f"Dropping cache entry {key}: no longer a valid {contract.__name__}")
            return None

    async def _store(self, key: str, value: Contract, ttl: int) -> None:
        """Cache a contract under ``key``, if there is a cache at all."""
        if self._cache is not None:
            await self._cache.set_json(key, value.model_dump(mode="json"), ttl)

    async def _drop_lists(self) -> None:
        """Drop every cached list page."""
        if self._cache is not None:
            await self._cache.delete_pattern(LIST_PATTERN)
