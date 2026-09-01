"""User orchestration: the bus plus the password work.

The router above this layer knows HTTP and nothing else; the client below it
knows the bus and nothing else. Users have no cache and no change
notifications, so unlike the tasks service this layer is thin -- what it owns
is the credential handling: passwords are hashed and verified here, in a
thread (bcrypt is CPU-bound and would stall the event loop), and the login
timing invariant lives here where no router can forget it.

Written in bus contracts, not in the HTTP schemas from ``api/schemas``:
importing those would point an inner layer at an outer one, and the auth
flows are also driven by OAuth redirects that have no request models.
"""

import asyncio
import logging
from typing import Any

import bcrypt
from task_tracker_common.contracts.commands import (
    UserCreateContract,
    UserUpdatePayloadContract,
    UserUpsertYandexContract,
)
from task_tracker_common.contracts.responses import UserAccount, UserData, UserList

from ..broker.users_client import UsersBusClient
from ..core.exceptions import InvalidCredentialsError, UserNotFoundError

logger = logging.getLogger(__name__)

# A real bcrypt hash used as a constant-time decoy when the username is
# unknown, so a failed login does the same work whether or not the user exists.
_DUMMY_HASH = "$2b$12$oOUmtFn7fm50bdt91.qyEelpY.SIYTtITMl8s4/O4evApDalGS.R2"


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt. Blocking; call via a thread."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt check. Never raises on a malformed or empty hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


class UserService:
    """Everything the gateway does with users, minus the HTTP."""

    def __init__(self, bus: UsersBusClient) -> None:
        """Take the bus client; there is nothing else to take."""
        self._bus = bus

    async def register(self, username: str, email: str, password: str) -> UserData:
        """Create a user from plaintext credentials.

        The plaintext stops here: only the hash goes onto the bus, so a
        worker log or a queue dump can never contain a password.
        """
        password_hash = await asyncio.to_thread(_hash_password, password)
        request = UserCreateContract(username=username, email=email, password_hash=password_hash)

        created = await self._bus.create(request)
        logger.info(f"User {created.id} registered")
        return created

    async def get(self, user_id: int) -> UserData:
        """Return one user."""
        return await self._bus.get(user_id)

    async def list_users(self, limit: int, offset: int) -> UserList:
        """Return one page of users plus the count over the whole table."""
        return await self._bus.list_users(limit=limit, offset=offset)

    async def update(self, user_id: int, changes: dict[str, Any]) -> UserData:
        """Apply a partial update.

        ``changes`` holds exactly the fields the caller named (the router
        dumps its schema with ``exclude_unset``); a plaintext ``password``
        among them is hashed and travels on as ``password_hash``.
        """
        if "password" in changes:
            changes["password_hash"] = await asyncio.to_thread(_hash_password, changes.pop("password"))

        updated = await self._bus.update(user_id, UserUpdatePayloadContract(**changes))
        logger.info(f"User {user_id} updated")
        return updated

    async def delete(self, user_id: int) -> None:
        """Delete a user."""
        await self._bus.delete(user_id)
        logger.info(f"User {user_id} deleted")

    async def authenticate(self, username: str, password: str) -> UserAccount:
        """Verify a username/password pair, or raise InvalidCredentialsError.

        The two failure causes -- unknown username and wrong password -- must
        be indistinguishable from the outside, in body and in timing alike.
        Hence one exception for both, and a decoy bcrypt round on the unknown-
        user path so both failures cost the same wall clock.
        """
        try:
            account = await self._bus.get_by_username(username)
        except UserNotFoundError:
            await asyncio.to_thread(_verify_password, password, _DUMMY_HASH)
            raise InvalidCredentialsError() from None

        ok = await asyncio.to_thread(_verify_password, password, account.password_hash or "")
        if not ok:
            raise InvalidCredentialsError()

        logger.info(f"Login success: user_id={account.id} username={account.username}")
        return account

    async def login_with_yandex(self, yandex_id: str, login: str, email: str) -> UserAccount:
        """Resolve a verified Yandex profile to a local account."""
        identity = UserUpsertYandexContract(yandex_id=yandex_id, login=login, email=email)

        account = await self._bus.upsert_yandex(identity)
        logger.info(f"OAuth login: user_id={account.id} username={account.username}")
        return account
