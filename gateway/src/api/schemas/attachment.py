"""Attachment schemas for Gateway API."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AttachmentCreate(BaseModel):
    """Schema for registering a new attachment."""

    task_id: int = Field(..., description="Task the attachment belongs to")
    filename: str = Field(..., min_length=1, max_length=255, description="Original file name")
    content_type: Optional[str] = Field(None, max_length=100, description="MIME type")
    storage_path: str = Field(..., min_length=1, description="Path/key in storage backend")
    size_bytes: Optional[int] = Field(None, ge=0, description="File size in bytes")


class AttachmentResponse(BaseModel):
    """Schema for attachment response."""

    id: int
    task_id: int
    filename: str
    content_type: Optional[str] = None
    storage_path: str
    size_bytes: Optional[int] = None
    uploaded_at: datetime


class AttachmentListResponse(BaseModel):
    """Schema for list of attachments response."""

    attachments: list[AttachmentResponse]
    total: int
