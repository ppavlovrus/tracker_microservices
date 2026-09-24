"""Yandex OAuth router: authorization code flow on top of Redis sessions.

The gateway never stores the Yandex access token -- it is used once to fetch
the profile, after which the user gets a regular local session cookie.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ...core.config import (
    COOKIE_SECURE,
    OAUTH_HTTP_TIMEOUT,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    YANDEX_CLIENT_ID,
    YANDEX_CLIENT_SECRET,
    YANDEX_OAUTH_BASE_URL,
    YANDEX_OAUTH_ENABLED,
    YANDEX_REDIRECT_URI,
    YANDEX_USERINFO_URL,
)
from ...core.exceptions import GatewayError
from ..deps import UsersServiceDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/yandex", tags=["auth"])

# Set in main.py lifespan.
session_store = None
state_store = None


def set_session_store(store) -> None:
    global session_store
    session_store = store


def set_state_store(store) -> None:
    global state_store
    state_store = store


class _OAuthAbortedError(Exception):
    """A recoverable failure: send the user back to login with a reason code.

    The flow has half a dozen ways to end early -- a reused state, a provider
    that declines, an unreachable endpoint, a profile without an email -- and
    every one of them ends identically, at the login page. Carrying the reason
    on an exception keeps each step free of the redirect it cannot build
    anyway, and keeps the endpoint from being a ladder of early returns.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _login_error_redirect(reason: str) -> RedirectResponse:
    """Send the user back to the login page with a displayable error code."""
    return RedirectResponse(url=f"/web/login?oauth_error={reason}", status_code=302)


def _require_callback_ready() -> None:
    """Refuse the callback unless OAuth is configured and its stores are up."""
    if not YANDEX_OAUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Yandex OAuth is not configured")
    if session_store is None or state_store is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


async def _accept_callback(code: str | None, state: str | None, error: str | None) -> str:
    """Burn the one-time state, then return the code Yandex sent back."""
    # Consume the state first so every exit path below burns it.
    if not await state_store.consume(state or ""):
        logger.warning("OAuth callback with unknown or reused state")
        raise _OAuthAbortedError("state")

    if error or not code:
        # The user declined access or Yandex reported a failure.
        logger.info(f"OAuth flow aborted by provider: error={error}")
        raise _OAuthAbortedError("declined")

    return code


async def _exchange_code(http: httpx.AsyncClient, code: str) -> str:
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
        raise _OAuthAbortedError("provider") from e

    if response.status_code != 200:
        logger.warning(f"Yandex token exchange failed: {response.status_code}")
        raise _OAuthAbortedError("provider")

    access_token = response.json().get("access_token")
    if not access_token:
        logger.warning("Yandex token response without access_token")
        raise _OAuthAbortedError("provider")

    return access_token


async def _fetch_profile(http: httpx.AsyncClient, access_token: str) -> dict[str, Any]:
    """Fetch the Yandex profile the freshly issued token unlocks."""
    try:
        response = await http.get(
            YANDEX_USERINFO_URL,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        )
    except httpx.HTTPError as e:
        logger.error(f"Yandex userinfo endpoint unreachable: {e}")
        raise _OAuthAbortedError("provider") from e

    if response.status_code != 200:
        logger.warning(f"Yandex userinfo failed: {response.status_code}")
        raise _OAuthAbortedError("provider")

    return response.json()


def _read_identity(profile: dict[str, Any]) -> tuple[str, str, str]:
    """Pull the three fields a local account needs out of the profile."""
    yandex_id = profile.get("id")
    login_name = profile.get("login")
    email = profile.get("default_email")
    if not yandex_id or not login_name or not email:
        # login:email scope missing or a mailbox-less account.
        logger.warning("Yandex profile lacks id/login/email, cannot log in")
        raise _OAuthAbortedError("profile")
    return str(yandex_id), login_name, email


async def _yandex_identity(code: str) -> tuple[str, str, str]:
    """Run the provider conversation: code -> token -> profile -> identity."""
    async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as http:
        access_token = await _exchange_code(http, code)
        profile = await _fetch_profile(http, access_token)
    return _read_identity(profile)


@router.get("/login")
async def yandex_login() -> RedirectResponse:
    """Start the flow: issue a CSRF state and redirect to Yandex."""
    if not YANDEX_OAUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Yandex OAuth is not configured")
    if state_store is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    state = await state_store.issue()
    if state is None:
        # No Redis -> no CSRF protection -> refuse to start the flow.
        raise HTTPException(status_code=503, detail="Session backend unavailable")

    params = urlencode(
        {
            "response_type": "code",
            "client_id": YANDEX_CLIENT_ID,
            "redirect_uri": YANDEX_REDIRECT_URI,
            "state": state,
        }
    )
    return RedirectResponse(url=f"{YANDEX_OAUTH_BASE_URL}/authorize?{params}", status_code=302)


@router.get("/callback")
async def yandex_callback(
    users: UsersServiceDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish the flow: verify state, exchange the code, log the user in."""
    _require_callback_ready()

    try:
        accepted = await _accept_callback(code, state, error)
        yandex_id, login_name, email = await _yandex_identity(accepted)
        account = await users.login_with_yandex(yandex_id=yandex_id, login=login_name, email=email)
    except _OAuthAbortedError as e:
        return _login_error_redirect(e.reason)
    except GatewayError as e:
        # The user is mid-redirect: any failure past this point -- timeout,
        # bus down, worker error -- ends the same way, back at the login page.
        logger.error(f"OAuth login failed against the users service: {e}")
        return _login_error_redirect("internal")

    token = await session_store.create({"id": account.id, "username": account.username, "email": account.email})
    if token is None:
        return _login_error_redirect("internal")

    response = RedirectResponse(url="/web/tasks", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    logger.info(f"OAuth login success: user_id={account.id} username={account.username}")
    return response
