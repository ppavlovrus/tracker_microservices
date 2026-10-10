"""Yandex OAuth router: authorization code flow on top of Redis sessions.

The gateway never stores the Yandex access token -- it is used once to fetch
the profile, after which the user gets a regular local session cookie.

What is left here is HTTP: the redirects that carry the user between the
login page, Yandex and the app. The conversation with the provider and the
stores lives in ``service/oauth.py``.
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ...core.config import (
    COOKIE_SECURE,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    YANDEX_CLIENT_ID,
    YANDEX_OAUTH_BASE_URL,
    YANDEX_OAUTH_ENABLED,
    YANDEX_REDIRECT_URI,
)
from ...service.oauth import OAuthAbortedError
from ..deps import OAuthServiceDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/yandex", tags=["auth"])


def _login_error_redirect(reason: str) -> RedirectResponse:
    """Send the user back to the login page with a displayable error code."""
    return RedirectResponse(url=f"/web/login?oauth_error={reason}", status_code=302)


@router.get("/login")
async def yandex_login(service: OAuthServiceDep) -> RedirectResponse:
    """Start the flow: issue a CSRF state and redirect to Yandex."""
    if not YANDEX_OAUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Yandex OAuth is not configured")

    state = await service.begin()

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
    service: OAuthServiceDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish the flow: verify state, exchange the code, log the user in."""
    if not YANDEX_OAUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Yandex OAuth is not configured")

    try:
        account, token = await service.complete(code, state, error)
    except OAuthAbortedError as e:
        return _login_error_redirect(e.reason)

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
