"""Attachment repository: every SQL statement the attachments worker runs."""

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_COLUMNS = "id, task_id, filename, content_type, storage_path, size_bytes, uploaded_at"


class AttachmentRepository:
    """Repository for Attachment entity operations."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with the pool every query acquires from."""
        self.pool = pool

    async def get_by_id(self, attachment_id: int) -> dict[str, Any] | None:
        """One attachment row by id, or None."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_COLUMNS}
                FROM attachment
                WHERE id = $1
                """,
                attachment_id,
            )
            return dict(row) if row else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert the metadata row; the foreign key is the only judge of the task."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO attachment (
                    task_id, filename, content_type, storage_path, size_bytes
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING {_COLUMNS}
                """,
                data["task_id"],
                data["filename"],
                data["content_type"],
                data["storage_path"],
                data["size_bytes"],
            )
            logger.info(f"Attachment created: ID={row['id']}, filename='{row['filename']}'")
            return dict(row)

    async def delete(self, attachment_id: int) -> bool:
        """Delete an attachment; False when the row was not there to delete."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM attachment WHERE id = $1", attachment_id)
            # The driver answers "DELETE 1" or "DELETE 0".
            return result.split()[-1] == "1"

    async def get_by_task_id(self, task_id: int) -> list[dict[str, Any]]:
        """Every attachment of one task, newest first."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_COLUMNS}
                FROM attachment
                WHERE task_id = $1
                ORDER BY uploaded_at DESC
                """,
                task_id,
            )
            return [dict(row) for row in rows]

    async def count_by_task_id(self, task_id: int) -> int:
        """Number of attachments on one task."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM attachment WHERE task_id = $1", task_id) or 0
