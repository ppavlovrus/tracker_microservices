"""Auth router for the Gateway: password login with Redis-backed sessions."""

import asyncio
import logging

import bcrypt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from typing import Annotated, Any, Dict, Optional

from ...config import (
    RPC_TIMEOUT,
    SESSION_TTL,
    SESSION_COOKIE_NAME,
    COOKIE_SECURE,
)
from ..schemas.auth import LoginRequest, LoginResponse, UserPublic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Set in main.py lifespan.
rabbitmq_client = None
session_store = None


def set_rabbitmq_client(client) -> None:
    global rabbitmq_client
    rabbitmq_client = client


def set_session_store(store) -> None:
    global session_store
    session_store = store


# A real bcrypt hash used as a constant-time decoy when the username is unknown,
# so a failed login does the same work whether or not the user exists.
_DUMMY_HASH = "$2b$12$oOUmtFn7fm50bdt91.qyEelpY.SIYTtITMl8s4/O4evApDalGS.R2"


def _verify_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt check. Never raises on a malformed hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def get_current_user(
    session_token: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve the session cookie to a user record, or None if unauthenticated."""
    if session_store is None or not session_token:
        return None
    return await session_store.get(session_token)


async def require_auth(
    user: Annotated[Optional[Dict[str, Any]], Depends(get_current_user)],
) -> Dict[str, Any]:
    """Dependency that rejects unauthenticated requests with 401."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, response: Response) -> LoginResponse:
    """Authenticate by username/password and start a session.

    Returns 401 on any failure (unknown user or wrong password) with the same
    generic message, so the response does not reveal whether a username exists.
    """
    if not rabbitmq_client or session_store is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        rpc = await rabbitmq_client.call(
            queue_name="users.commands",
            message={
                "command": "get_user_by_username",
                "data": {"username": credentials.username},
            },
            timeout=RPC_TIMEOUT,
        )
    except TimeoutError:
        logger.error("Timeout waiting for Users service during login")
        raise HTTPException(status_code=504, detail="Users service timeout")

    invalid = HTTPException(status_code=401, detail="Invalid username or password")

    # bcrypt is CPU-bound and would block the event loop; run it in a thread.
    if not rpc.get("success"):
        # Hash a dummy value anyway to keep timing roughly constant (no enumeration).
        await asyncio.to_thread(_verify_password, credentials.password, _DUMMY_HASH)
        raise invalid

    user = rpc["data"]
    ok = await asyncio.to_thread(
        _verify_password, credentials.password, user.get("password_hash", "")
    )
    if not ok:
        raise invalid

    token = await session_store.create(user)
    if token is None:
        # Session backend is down -- fail closed rather than fake a login.
        raise HTTPException(status_code=503, detail="Session backend unavailable")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    logger.info(f"Login success: user_id={user['id']} username={user['username']}")
    return LoginResponse(user=UserPublic(**user))


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session_token: Annotated[Optional[str], Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    """End the current session and clear the cookie. Idempotent."""
    if session_store is not None and session_token:
        await session_store.delete(session_token)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserPublic)
async def me(
    user: Annotated[Dict[str, Any], Depends(require_auth)],
) -> UserPublic:
    """Return the currently authenticated user."""
    return UserPublic(id=user["user_id"], username=user["username"], email=user.get("email"))
