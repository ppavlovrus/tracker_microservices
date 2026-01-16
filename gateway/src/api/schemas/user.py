"""User schemas for Gateway API."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Schema for creating a new user (registration)."""
    
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=100, description="User password")


class UserUpdate(BaseModel):
    """Schema for updating user (all fields optional)."""
    
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8, max_length=100)


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
