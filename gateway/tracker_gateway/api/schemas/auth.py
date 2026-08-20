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
    """Returned on successful login."""

    user: UserPublic
