"""Auth router for the Gateway: password login with Redis-backed sessions.

The credential work -- the lookup, the bcrypt rounds, the rule that an
unknown username and a wrong password must be one indistinguishable failure --
lives in the user service. What remains here is HTTP: the cookie, the session
records, and the access token for API clients.

A login answers both authentication paths at once: the browser gets its
session cookie, and an API client gets a Bearer token in the body. The OAuth
callback cannot do the second half -- a 302 redirect has no body to read --
so the redirect flow stays on cookies alone.
"""

import logging
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response

from ...core.config import (
    COOKIE_SECURE,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
)
from ...core.security import bearer_token, create_access_token, decode_access_token
from ..deps import UsersServiceDep
from ..schemas.auth import LoginRequest, LoginResponse, UserPublic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Set in main.py lifespan.
session_store = None


def set_session_store(store) -> None:
    global session_store
    session_store = store


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> dict[str, Any] | None:
    """Resolve the caller: a Bearer token first, then the session cookie.

    Both paths answer with the session record's shape -- ``user_id``,
    ``username``, ``email`` -- so the caller cannot tell which one applied.
    A token that does not verify resolves to no user, same as a missing
    cookie: the distinct expired/invalid wording belongs to the middleware,
    which serves clients that act on it.
    """
    token = bearer_token(authorization)
    if token is not None:
        try:
            claims = decode_access_token(token)
        except jwt.PyJWTError:
            return None
        return {"user_id": int(claims["sub"]), "username": claims["username"], "email": claims.get("email")}

    if session_store is None or not session_token:
        return None
    return await session_store.get(session_token)


async def require_auth(
    user: Annotated[dict[str, Any] | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Dependency that rejects unauthenticated requests with 401."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, response: Response, users: UsersServiceDep) -> LoginResponse:
    """Authenticate by username/password and start a session.

    Answers 401 on any failure (unknown user or wrong password) with the same
    generic message: ``authenticate`` raises one InvalidCredentialsError for
    both causes, so this router could not tell them apart if it tried.
    """
    if session_store is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    account = await users.authenticate(credentials.username, credentials.password)

    token = await session_store.create({"id": account.id, "username": account.username, "email": account.email})
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
    # The same identity, signed for API clients: no cookie jar, no store
    # round-trip, its own expiry.
    access_token = create_access_token({"id": account.id, "username": account.username, "email": account.email})
    return LoginResponse(
        user=UserPublic(id=account.id, username=account.username, email=account.email),
        access_token=access_token,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    """End the current session and clear the cookie. Idempotent."""
    if session_store is not None and session_token:
        await session_store.delete(session_token)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserPublic)
async def me(
    user: Annotated[dict[str, Any], Depends(require_auth)],
) -> UserPublic:
    """Return the currently authenticated user."""
    return UserPublic(id=user["user_id"], username=user["username"], email=user.get("email"))
