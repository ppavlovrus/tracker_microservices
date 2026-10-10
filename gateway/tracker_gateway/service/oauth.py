"""OAuth login flow: the conversation with Yandex and the local session.

The router above this layer knows HTTP and redirects; everything between --
burning the one-time state, trading the code for a token, reading the
profile, resolving it to a local account, issuing the session -- happens
here. The provider's HTTP client is part of the flow rather than a separate
port: it is sixty lines with one caller, and a second provider is the day it
earns its own module.
"""

import logging
from typing import Any

import httpx
from task_tracker_common.contracts.responses import UserAccount

from ..core.config import (
    OAUTH_HTTP_TIMEOUT,
    YANDEX_CLIENT_ID,
    YANDEX_CLIENT_SECRET,
    YANDEX_OAUTH_BASE_URL,
    YANDEX_USERINFO_URL,
)
from ..core.exceptions import GatewayError, SessionStoreUnavailableError
from ..storage.sessions import OAuthStateStore, SessionStore
from .users import UserService

logger = logging.getLogger(__name__)


class OAuthAbortedError(Exception):
    """A recoverable failure: send the user back to the login page with a reason.

    The flow has half a dozen ways to end early -- a reused state, a provider
    that declines, an unreachable endpoint, a profile without an email -- and
    every one of them ends identically, at the login page. Carrying the reason
    on an exception keeps each step free of the redirect it cannot build
    anyway, and keeps the caller from being a ladder of early returns.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class OAuthService:
    """Everything the gateway does during a Yandex login, minus the HTTP."""

    def __init__(
        self,
        state_store: OAuthStateStore | None,
        session_store: SessionStore | None,
        users: UserService,
    ) -> None:
        """Take the collaborators; the stores may be absent when their feature is off."""
        self._state_store = state_store
        self._session_store = session_store
        self._users = users

    async def begin(self) -> str:
        """Issue a one-time CSRF state for a new login attempt."""
        self._require_stores()

        state = await self._state_store.issue()
        if state is None:
            # No Redis -> no CSRF protection -> refuse to start the flow.
            raise SessionStoreUnavailableError()
        return state

    async def complete(self, code: str | None, state: str | None, error: str | None) -> tuple[UserAccount, str]:
        """Finish the flow: verify the state, talk to the provider, log in.

        Returns the account and the session token to hand out as a cookie.
        """
        self._require_stores()

        accepted = await self._accept_callback(code, state, error)
        yandex_id, login_name, email = await self._yandex_identity(accepted)

        try:
            account = await self._users.login_with_yandex(yandex_id=yandex_id, login=login_name, email=email)
        except GatewayError as e:
            # The user is mid-redirect: any failure past this point -- timeout,
            # bus down, worker error -- ends the same way, back at the login page.
            logger.error(f"OAuth login failed against the users service: {e}")
            raise OAuthAbortedError("internal") from e

        session = {"id": account.id, "username": account.username, "email": account.email}
        token = await self._session_store.create(session)
        if token is None:
            raise OAuthAbortedError("internal")

        return account, token

    # -- the stores ---------------------------------------------------------

    def _require_stores(self) -> None:
        """Refuse the flow unless both stores are up."""
        if self._state_store is None or self._session_store is None:
            raise SessionStoreUnavailableError()

    # -- the provider conversation ------------------------------------------

    async def _accept_callback(self, code: str | None, state: str | None, error: str | None) -> str:
        """Burn the one-time state, then return the code Yandex sent back."""
        # Consume the state first so every exit path below burns it.
        if not await self._state_store.consume(state or ""):
            logger.warning("OAuth callback with unknown or reused state")
            raise OAuthAbortedError("state")

        if error or not code:
            # The user declined access or Yandex reported a failure.
            logger.info(f"OAuth flow aborted by provider: error={error}")
            raise OAuthAbortedError("declined")

        return code

    async def _exchange_code(self, http: httpx.AsyncClient, code: str) -> str:
        """Trade the authorization code for an access token."""
        try:
            response = await http.post(
                f"{YANDEX_OAUTH_BASE_URL}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": YANDEX_CLIENT_ID,
                    "client_secret": YANDEX_CLIENT_SECRET,
                },
            )
        except httpx.HTTPError as e:
            logger.error(f"Yandex token endpoint unreachable: {e}")
            raise OAuthAbortedError("provider") from e

        if response.status_code != 200:
            logger.warning(f"Yandex token exchange failed: {response.status_code}")
            raise OAuthAbortedError("provider")

        access_token = response.json().get("access_token")
        if not access_token:
            logger.warning("Yandex token response without access_token")
            raise OAuthAbortedError("provider")

        return access_token

    async def _fetch_profile(self, http: httpx.AsyncClient, access_token: str) -> dict[str, Any]:
        """Fetch the Yandex profile the freshly issued token unlocks."""
        try:
            response = await http.get(
                YANDEX_USERINFO_URL,
                params={"format": "json"},
                headers={"Authorization": f"OAuth {access_token}"},
            )
        except httpx.HTTPError as e:
            logger.error(f"Yandex userinfo endpoint unreachable: {e}")
            raise OAuthAbortedError("provider") from e

        if response.status_code != 200:
            logger.warning(f"Yandex userinfo failed: {response.status_code}")
            raise OAuthAbortedError("provider")

        return response.json()

    def _read_identity(self, profile: dict[str, Any]) -> tuple[str, str, str]:
        """Pull the three fields a local account needs out of the profile."""
        yandex_id = profile.get("id")
        login_name = profile.get("login")
        email = profile.get("default_email")
        if not yandex_id or not login_name or not email:
            # login:email scope missing or a mailbox-less account.
            logger.warning("Yandex profile lacks id/login/email, cannot log in")
            raise OAuthAbortedError("profile")
        return str(yandex_id), login_name, email

    async def _yandex_identity(self, code: str) -> tuple[str, str, str]:
        """Run the provider conversation: code -> token -> profile -> identity."""
        async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as http:
            access_token = await self._exchange_code(http, code)
            profile = await self._fetch_profile(http, access_token)
        return self._read_identity(profile)
