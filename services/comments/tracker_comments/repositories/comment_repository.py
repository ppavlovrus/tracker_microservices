"""Comment repository: every SQL statement the comments worker runs."""

import logging
from datetime import datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_COLUMNS = "id, task_id, user_id, content, created_at, updated_at"


class CommentRepository:
    """Repository for Comment entity operations."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with the pool every query acquires from."""
        self.pool = pool

    async def get_by_id(self, comment_id: int) -> dict[str, Any] | None:
        """One comment row by id, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_COLUMNS}
                FROM comment
                WHERE id = $1
                """,
                comment_id,
            )
            return dict(row) if row else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a comment; the foreign keys are the only judge of its references."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO comment (task_id, user_id, content)
                VALUES ($1, $2, $3)
                RETURNING {_COLUMNS}
                """,
                data["task_id"],
                data["user_id"],
                data["content"],
            )
            logger.info(f"Comment created: ID={row['id']} for task_id={row['task_id']}")
            return dict(row)

    async def update(self, comment_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Replace the content and touch ``updated_at``, or None if there is no such row.

        ``updated_at`` is written here rather than left to the column default:
        a server default fires on INSERT, and Postgres has no ON UPDATE -- the
        same reason the tasks repository writes it explicitly.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE comment
                SET content = $1, updated_at = $2
                WHERE id = $3
                RETURNING {_COLUMNS}
                """,
                data["content"],
                datetime.utcnow(),
                comment_id,
            )
            return dict(row) if row else None

    async def delete(self, comment_id: int) -> bool:
        """Delete a comment; False when the row was not there to delete."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM comment WHERE id = $1", comment_id)
            # The driver answers "DELETE 1" or "DELETE 0".
            return result.split()[-1] == "1"

    async def get_by_task_id(self, task_id: int) -> list[dict[str, Any]]:
        """Every comment of one task, oldest first."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_COLUMNS}
                FROM comment
                WHERE task_id = $1
                ORDER BY created_at ASC
                """,
                task_id,
            )
            return [dict(row) for row in rows]

    async def count_by_task_id(self, task_id: int) -> int:
        """Number of comments on one task."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM comment WHERE task_id = $1", task_id) or 0
