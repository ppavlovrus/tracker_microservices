"""User schemas (DTOs)."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("username")
    @classmethod
    def username_to_lower(cls, v: str) -> str:
        """Convert username to lowercase."""
        return v.lower()

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: str) -> str:
        """Convert email to lowercase."""
        return v.lower()


class UserUpdate(BaseModel):
    """Schema for updating user (all fields optional)."""

    username: Optional[str] = Field(None, min_length=3, max_length=64)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)

    @field_validator("username")
    @classmethod
    def username_to_lower(cls, v: Optional[str]) -> Optional[str]:
        """Convert username to lowercase if provided."""
        return v.lower() if v else v

    @field_validator("email")
    @classmethod
    def email_to_lower(cls, v: Optional[str]) -> Optional[str]:
        """Convert email to lowercase if provided."""
        return v.lower() if v else v


class UserResponse(BaseModel):
    """Schema for user response (without password)."""

    id: int
    username: str
    email: str
    created_at: datetime
    last_login: Optional[datetime] = None


class UserListResponse(BaseModel):
    """Schema for list of users."""

    items: List[UserResponse]
    limit: int
    offset: int

