"""User schemas for Gateway API."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from .partial import PartialUpdate, reject_null


class UserCreate(BaseModel):
    """Schema for creating a new user (registration)."""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=100, description="User password")


class UserUpdate(PartialUpdate):
    """Schema for updating user (all fields optional).

    None of the three may be set to null: ``username`` and ``email`` back NOT
    NULL columns, and a null password is not a password. Leaving a field out
    is how a partial update says "do not touch this one".
    """

    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8, max_length=100)

    @field_validator("username", "email", "password")
    @classmethod
    def _not_nullable(cls, v: object) -> object:
        return reject_null(v)


class UserResponse(BaseModel):
    """Schema for user response (without password_hash)."""

    id: int
    username: str
    email: str
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Schema for list of users response."""

    users: list[UserResponse]
    total: int
    limit: int
    offset: int
