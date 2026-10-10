"""Tag repository: every SQL statement the tags worker runs."""

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class TagRepository:
    """Repository for Tag entity operations."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with the pool every query acquires from."""
        self.pool = pool

    async def get_by_id(self, tag_id: int) -> dict[str, Any] | None:
        """One tag row by id, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name
                FROM tag
                WHERE id = $1
                """,
                tag_id,
            )
            return dict(row) if row else None

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        """One tag row by name, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name
                FROM tag
                WHERE name = $1
                """,
                name,
            )
            return dict(row) if row else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a tag; the unique constraint on name is the only judge."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tag (name)
                VALUES ($1)
                RETURNING id, name
                """,
                data["name"],
            )
            logger.info(f"Tag created: ID={row['id']}")
            return dict(row)

    async def update(self, tag_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Rename a tag, or None if there is no such row."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE tag
                SET name = $1
                WHERE id = $2
                RETURNING id, name
                """,
                data["name"],
                tag_id,
            )
            return dict(row) if row else None

    async def delete(self, tag_id: int) -> bool:
        """Delete a tag; False when the row was not there to delete."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM tag WHERE id = $1", tag_id)
            # The driver answers "DELETE 1" or "DELETE 0".
            return result.split()[-1] == "1"

    async def get_all(self, limit: int, offset: int) -> list[dict[str, Any]]:
        """One page of tags, ordered by name."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name
                FROM tag
                ORDER BY name ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            return [dict(row) for row in rows]

    async def count_all(self) -> int:
        """Total number of tags."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM tag") or 0
