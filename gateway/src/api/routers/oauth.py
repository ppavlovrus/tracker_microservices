"""Yandex OAuth router: authorization code flow on top of Redis sessions.

The gateway never stores the Yandex access token -- it is used once to fetch
the profile, after which the user gets a regular local session cookie.
"""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ...config import (
    COOKIE_SECURE,
    OAUTH_HTTP_TIMEOUT,
    RPC_TIMEOUT,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    YANDEX_CLIENT_ID,
    YANDEX_CLIENT_SECRET,
    YANDEX_OAUTH_BASE_URL,
    YANDEX_OAUTH_ENABLED,
    YANDEX_REDIRECT_URI,
    YANDEX_USERINFO_URL,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/yandex", tags=["auth"])

# Set in main.py lifespan.
rabbitmq_client = None
session_store = None
state_store = None


def set_rabbitmq_client(client) -> None:
    global rabbitmq_client
    rabbitmq_client = client


def set_session_store(store) -> None:
    global session_store
    session_store = store


def set_state_store(store) -> None:
    global state_store
    state_store = store


def _login_error_redirect(reason: str) -> RedirectResponse:
    """Send the user back to the login page with a displayable error code."""
    return RedirectResponse(url=f"/web/login?oauth_error={reason}", status_code=302)


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
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish the flow: verify state, exchange the code, log the user in."""
    if not YANDEX_OAUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Yandex OAuth is not configured")
    if rabbitmq_client is None or session_store is None or state_store is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Consume the state first so every exit path below burns it.
    if not await state_store.consume(state or ""):
        logger.warning("OAuth callback with unknown or reused state")
        return _login_error_redirect("state")

    if error or not code:
        # The user declined access or Yandex reported a failure.
        logger.info(f"OAuth flow aborted by provider: error={error}")
        return _login_error_redirect("declined")

    async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as http:
        try:
            token_resp = await http.post(
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
            return _login_error_redirect("provider")

        if token_resp.status_code != 200:
            logger.warning(f"Yandex token exchange failed: {token_resp.status_code}")
            return _login_error_redirect("provider")

        access_token = token_resp.json().get("access_token")
        if not access_token:
            logger.warning("Yandex token response without access_token")
            return _login_error_redirect("provider")

        try:
            info_resp = await http.get(
                YANDEX_USERINFO_URL,
                params={"format": "json"},
                headers={"Authorization": f"OAuth {access_token}"},
            )
        except httpx.HTTPError as e:
            logger.error(f"Yandex userinfo endpoint unreachable: {e}")
            return _login_error_redirect("provider")

    if info_resp.status_code != 200:
        logger.warning(f"Yandex userinfo failed: {info_resp.status_code}")
        return _login_error_redirect("provider")

    profile = info_resp.json()
    yandex_id = profile.get("id")
    yandex_login_name = profile.get("login")
    email = profile.get("default_email")
    if not yandex_id or not yandex_login_name or not email:
        # login:email scope missing or a mailbox-less account.
        logger.warning("Yandex profile lacks id/login/email, cannot log in")
        return _login_error_redirect("profile")

    try:
        rpc = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "upsert_yandex_user",
                "data": {
                    "yandex_id": str(yandex_id),
                    "login": yandex_login_name,
                    "email": email,
                },
            },
            timeout=RPC_TIMEOUT,
        )
    except TimeoutError:
        logger.error("Timeout waiting for Users service during OAuth login")
        return _login_error_redirect("internal")

    if not rpc.get("success"):
        logger.error(f"upsert_yandex_user failed: {rpc.get('error')}")
        return _login_error_redirect("internal")

    user = rpc["data"]
    token = await session_store.create(user)
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
    logger.info(f"OAuth login success: user_id={user['id']} username={user['username']}")
    return response
