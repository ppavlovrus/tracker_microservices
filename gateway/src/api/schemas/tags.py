"""Tag schemas for Gateway API."""

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """Schema for creating a new tag."""

    name: str = Field(..., min_length=1, max_length=100, description="Tag name")


class TagUpdate(BaseModel):
    """Schema for updating a tag."""

    name: str = Field(..., min_length=1, max_length=100, description="Tag name")


class TagResponse(BaseModel):
    """Schema for tag response."""

    id: int
    name: str


class TagListResponse(BaseModel):
    """Schema for list of tags response."""

    tags: list[TagResponse]
    total: int
    limit: int
    offset: int
