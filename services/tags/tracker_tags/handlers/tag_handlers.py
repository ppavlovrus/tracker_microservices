"""Tag command handlers for RabbitMQ messages.

A handler receives a command contract the dispatcher has already validated,
and answers with an envelope built from the shared response contracts. No
raw payload dicts, no hand-written ``{"success": ...}`` literals.

Uniqueness is not pre-checked with a SELECT: two concurrent creates would
both pass such a check and one would still hit the constraint. The database
is the only judge; ``UniqueViolationError`` is caught and translated.
"""

import logging
from typing import Any

import asyncpg
from task_tracker_common.contracts.commands import (
    TagCreationContract,
    TagDeleteContract,
    TagGetByIdContract,
    TagGetByNameContract,
    TagListContract,
    TagUpdateContract,
)
from task_tracker_common.contracts.responses import (
    ErrorCode,
    TagData,
    TagDelete,
    TagList,
    rpc_error,
    rpc_ok,
)

from ..repositories.tag_repository import TagRepository

logger = logging.getLogger(__name__)

# The gateway turns this into the 404 body, so the wording is observable.
TAG_NOT_FOUND = "Tag not found"

Envelope = dict[str, Any]


def _conflict(exc: asyncpg.UniqueViolationError) -> Envelope:
    """Translate a unique-constraint violation into a CONFLICT envelope.

    ``tag_name_key`` is the only unique constraint on the table, so there is
    nothing to branch on. ``error_type`` still names the field: it is the
    machine-readable half the gateway picks its domain error from, rather
    than parsing the message.
    """
    return rpc_error(ErrorCode.CONFLICT, "Tag with this name already exists", "name")


class TagHandlers:
    """Handlers for tag-related commands."""

    def __init__(self, repository: TagRepository):
        """Initialize handlers with the repository they read and write through."""
        self.repository = repository

    async def handle_create_tag(self, command: TagCreationContract) -> Envelope:
        """Handle ``create_tag``: insert the row, answer with the stored tag."""
        try:
            tag = await self.repository.create(command.model_dump())
        except asyncpg.UniqueViolationError as e:
            logger.warning(f"Tag creation conflict: {e.constraint_name}")
            return _conflict(e)

        logger.info(f"Tag created successfully: ID={tag['id']}")
        return rpc_ok(TagData, tag)

    async def handle_get_tag(self, command: TagGetByIdContract) -> Envelope:
        """Handle ``get_tag``: one tag row by id."""
        tag = await self.repository.get_by_id(command.id)

        if tag is None:
            logger.warning(f"Tag not found: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, TAG_NOT_FOUND)

        return rpc_ok(TagData, tag)

    async def handle_get_tag_by_name(self, command: TagGetByNameContract) -> Envelope:
        """Handle ``get_tag_by_name``: resolve a tag by name.

        The tasks gateway uses this to find a tag before linking it to a
        task, creating it when the name is new.
        """
        tag = await self.repository.get_by_name(command.name)

        if tag is None:
            logger.warning(f"Tag not found by name: {command.name}")
            return rpc_error(ErrorCode.NOT_FOUND, TAG_NOT_FOUND)

        return rpc_ok(TagData, tag)

    async def handle_update_tag(self, command: TagUpdateContract) -> Envelope:
        """Handle ``update_tag``: rename a tag.

        Renaming to a name another tag already holds is a conflict the
        database reports, not something to pre-check -- a pre-check would
        race a concurrent create and lose.
        """
        try:
            tag = await self.repository.update(command.id, command.update.model_dump())
        except asyncpg.UniqueViolationError as e:
            logger.warning(f"Tag update conflict: {e.constraint_name}")
            return _conflict(e)

        if tag is None:
            logger.warning(f"Tag not found for update: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, TAG_NOT_FOUND)

        logger.info(f"Tag updated successfully: ID={command.id}")
        return rpc_ok(TagData, tag)

    async def handle_delete_tag(self, command: TagDeleteContract) -> Envelope:
        """Handle ``delete_tag``: remove the row (task links cascade)."""
        deleted = await self.repository.delete(command.id)

        if not deleted:
            logger.warning(f"Tag not found for deletion: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, TAG_NOT_FOUND)

        logger.info(f"Tag deleted successfully: ID={command.id}")
        return rpc_ok(TagDelete, {"id": command.id, "deleted": True})

    async def handle_list_tags(self, command: TagListContract) -> Envelope:
        """Handle ``list_tags``: one page, and the total it comes from."""
        tags = await self.repository.get_all(limit=command.limit, offset=command.offset)
        total = await self.repository.count_all()

        logger.debug(f"Listed {len(tags)} tags (total={total}, limit={command.limit}, offset={command.offset})")
        return rpc_ok(TagList, {"tags": tags, "total": total})
