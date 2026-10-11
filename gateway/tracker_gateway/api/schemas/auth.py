"""Schemas for the auth endpoints."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials for password login."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=100)


class UserPublic(BaseModel):
    """Authenticated user, safe to return to clients (no password hash)."""

    id: int
    username: str
    email: str | None = None


class LoginResponse(BaseModel):
    """Returned on successful login: the user, plus a token for API clients.

    The browser keeps using the session cookie this response also sets; the
    ``access_token`` is for clients that authenticate with
    ``Authorization: Bearer`` and own no cookie jar.
    """

    user: UserPublic
    access_token: str
