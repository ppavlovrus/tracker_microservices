"""User command handlers for RabbitMQ messages.

A handler receives a command contract that the dispatcher has already
validated, and answers with an envelope built from the shared response
contracts. The raw payload dict and hand-written ``{"success": ...}``
literals are gone, and so is the field-by-field date serialisation -- the
response contract owns the shape and ``rpc_ok`` dumps it in JSON mode.

Two answer shapes leave this service. ``UserData`` is the public one and has
no ``password_hash`` field at all, so a public query that accidentally
selects the hash fails validation here rather than leaking. ``UserAccount``
carries the credentials and answers only the auth lookups.

Uniqueness is not pre-checked with a SELECT: two concurrent creates would
both pass such a check and one would still hit the constraint. The database
is the only judge; ``UniqueViolationError`` is caught and translated instead.
"""

import logging
from typing import Any

import asyncpg
from task_tracker_common.contracts.commands import (
    UserCreateContract,
    UserDeleteContract,
    UserGetByEmailContract,
    UserGetByIdContract,
    UserGetByUsernameContract,
    UserListContract,
    UserUpdateContract,
    UserUpsertYandexContract,
)
from task_tracker_common.contracts.responses import (
    ErrorCode,
    UserAccount,
    UserData,
    UserDelete,
    UserList,
    rpc_error,
    rpc_ok,
)

from ..repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# The gateway turns this into the 404 body, so the wording is observable.
USER_NOT_FOUND = "User not found"

Envelope = dict[str, Any]


def _conflict(exc: asyncpg.UniqueViolationError) -> Envelope:
    """Translate a unique-constraint violation into a CONFLICT envelope.

    The constraint name says which field collided; ``error_type`` carries it
    as the machine-readable half so the gateway can pick the matching domain
    error without parsing the message.
    """
    if exc.constraint_name == "user_username_key":
        return rpc_error(ErrorCode.CONFLICT, "Username already exists", "username")
    return rpc_error(ErrorCode.CONFLICT, "Email already exists", "email")


class UserHandlers:
    """Handlers for user-related commands."""

    def __init__(self, repository: UserRepository):
        """Initialize handlers with the repository they read and write through."""
        self.repository = repository

    async def handle_create_user(self, command: UserCreateContract) -> Envelope:
        """Handle ``create_user``: insert the row, answer with the stored user."""
        try:
            user = await self.repository.create(command.model_dump())
        except asyncpg.UniqueViolationError as e:
            logger.warning(f"User creation conflict: {e.constraint_name}")
            return _conflict(e)

        logger.info(f"User created successfully: ID={user['id']}")
        return rpc_ok(UserData, user)

    async def handle_get_user(self, command: UserGetByIdContract) -> Envelope:
        """Handle ``get_user``: one public user row."""
        user = await self.repository.get_by_id(command.id)

        if user is None:
            logger.warning(f"User not found: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, USER_NOT_FOUND)

        logger.debug(f"User retrieved: ID={command.id}")
        return rpc_ok(UserData, user)

    async def handle_get_user_by_email(self, command: UserGetByEmailContract) -> Envelope:
        """Handle ``get_user_by_email``: credential lookup by email."""
        user = await self.repository.get_by_email(command.email)

        if user is None:
            return rpc_error(ErrorCode.NOT_FOUND, USER_NOT_FOUND)

        logger.debug(f"User retrieved by email: {command.email}")
        return rpc_ok(UserAccount, user)

    async def handle_get_user_by_username(self, command: UserGetByUsernameContract) -> Envelope:
        """Handle ``get_user_by_username``: the login lookup.

        Answers with ``UserAccount`` -- including ``password_hash``, because
        verifying it is the caller's whole purpose. The gateway is responsible
        for never letting the hash travel further.
        """
        user = await self.repository.get_by_username(command.username)

        if user is None:
            return rpc_error(ErrorCode.NOT_FOUND, USER_NOT_FOUND)

        logger.debug(f"User retrieved by username: {command.username}")
        return rpc_ok(UserAccount, user)

    async def handle_upsert_yandex_user(self, command: UserUpsertYandexContract) -> Envelope:
        """Handle ``upsert_yandex_user`` (Yandex OAuth login).

        Resolution order:
        1. A user already linked to this Yandex id -- return it.
        2. A user with the same email -- link the Yandex id to it. Safe because
           Yandex only reports emails it has verified itself.
        3. Otherwise create a new user without a local password.
        """
        user = await self.repository.get_by_yandex_id(command.yandex_id)
        if user:
            logger.debug(f"OAuth login: existing user ID={user['id']}")
            return rpc_ok(UserAccount, user)

        existing = await self.repository.get_by_email(command.email)
        if existing:
            user = await self.repository.link_yandex_id(existing["id"], command.yandex_id)
            if user is None:
                return rpc_error(ErrorCode.NOT_FOUND, USER_NOT_FOUND)
            logger.info(f"OAuth login: linked yandex_id to user ID={user['id']}")
            return rpc_ok(UserAccount, user)

        try:
            user = await self.repository.create_oauth(command.login, command.email, command.yandex_id)
        except asyncpg.UniqueViolationError:
            # The Yandex login is taken as a local username; fall back to a
            # deterministic unique name derived from the Yandex id.
            fallback = f"{command.login}_ya{command.yandex_id}"[:64]
            user = await self.repository.create_oauth(fallback, command.email, command.yandex_id)

        logger.info(f"OAuth login: created user ID={user['id']}")
        return rpc_ok(UserAccount, user)

    async def handle_update_user(self, command: UserUpdateContract) -> Envelope:
        """Handle ``update_user``: write the fields the caller actually set.

        ``exclude_unset`` is what makes this a partial update: a field the
        caller never mentioned is absent from the dump, so the repository's
        dynamic UPDATE leaves the column alone.
        """
        update = command.update.model_dump(exclude_unset=True)

        if not update:
            return rpc_error(ErrorCode.VALIDATION_ERROR, "No fields to update")

        try:
            user = await self.repository.update(command.id, update)
        except asyncpg.UniqueViolationError as e:
            logger.warning(f"User update conflict: ID={command.id}, {e.constraint_name}")
            return _conflict(e)

        if user is None:
            logger.warning(f"User not found for update: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, USER_NOT_FOUND)

        logger.info(f"User updated successfully: ID={command.id}")
        return rpc_ok(UserData, user)

    async def handle_delete_user(self, command: UserDeleteContract) -> Envelope:
        """Handle ``delete_user``: report whether the row was there to delete."""
        deleted = await self.repository.delete(command.id)

        if not deleted:
            logger.warning(f"User not found for deletion: ID={command.id}")
            return rpc_error(ErrorCode.NOT_FOUND, USER_NOT_FOUND)

        logger.info(f"User deleted successfully: ID={command.id}")
        return rpc_ok(UserDelete, {"id": command.id, "deleted": True})

    async def handle_list_users(self, command: UserListContract) -> Envelope:
        """Handle ``list_users``: one page plus the count over the whole table.

        ``total`` is deliberately not ``len(users)``: the caller pages on it,
        and a page length would make the last page look like the whole set.
        """
        users = await self.repository.get_all(limit=command.limit, offset=command.offset)
        total = await self.repository.count_all()

        logger.debug(f"Listed {len(users)} users (total={total}, limit={command.limit}, offset={command.offset})")
        return rpc_ok(UserList, {"users": users, "total": total})
