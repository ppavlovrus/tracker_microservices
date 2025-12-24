"""Attachment repository."""
from typing import Optional, List, Dict, Any
from task_tracker_common.repository import BaseRepository


class AttachmentRepository(BaseRepository):
    """Repository for Attachment entity."""

    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get attachment by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM attachment WHERE id = $1",
                id
            )
            return dict(row) if row else None

    async def get_by_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Get all attachments for a specific task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM attachment
                WHERE task_id = $1
                ORDER BY uploaded_at DESC
                """,
                task_id
            )
            return [dict(row) for row in rows]

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new attachment."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO attachment (task_id, filename, content_type, storage_path, size_bytes)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                data["task_id"],
                data["filename"],
                data.get("content_type"),
                data["storage_path"],
                data.get("size_bytes")
            )
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update attachment metadata."""
        async with self.pool.acquire() as conn:
            fields = []
            values = []
            idx = 1

            for key, value in data.items():
                fields.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

            values.append(id)

            query = f"""
                UPDATE attachment
                SET {', '.join(fields)}
                WHERE id = ${idx}
                RETURNING *
            """

            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None

    async def delete(self, id: int) -> bool:
        """Delete attachment."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM attachment WHERE id = $1",
                id
            )
            return int(result.split()[-1]) > 0

    async def delete_by_task(self, task_id: int) -> int:
        """Delete all attachments for a task. Returns count of deleted attachments."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM attachment WHERE task_id = $1",
                task_id
            )
            return int(result.split()[-1])

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all attachments with pagination."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM attachment
                ORDER BY uploaded_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def get_total_size_for_task(self, task_id: int) -> int:
        """Get total size of all attachments for a task in bytes."""
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM attachment WHERE task_id = $1",
                task_id
            )
            return total or 0

    async def count_by_task(self, task_id: int) -> int:
        """Count attachments for a task."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM attachment WHERE task_id = $1",
                task_id
            )
            return count



