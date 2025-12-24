"""Comment repository."""
from typing import Optional, List, Dict, Any
from task_tracker_common.repository import BaseRepository


class CommentRepository(BaseRepository):
    """Repository for Comment entity."""

    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get comment by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM comment WHERE id = $1",
                id
            )
            return dict(row) if row else None

    async def get_by_task(self, task_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all comments for a specific task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM comment
                WHERE task_id = $1
                ORDER BY created_at ASC
                LIMIT $2 OFFSET $3
                """,
                task_id,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def get_by_user(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all comments by a specific user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM comment
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new comment."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO comment (task_id, user_id, content)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                data["task_id"],
                data["user_id"],
                data["content"]
            )
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update comment content."""
        async with self.pool.acquire() as conn:
            # Always update updated_at
            row = await conn.fetchrow(
                """
                UPDATE comment
                SET content = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING *
                """,
                data["content"],
                id
            )
            return dict(row) if row else None

    async def delete(self, id: int) -> bool:
        """Delete comment."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM comment WHERE id = $1",
                id
            )
            return int(result.split()[-1]) > 0

    async def delete_by_task(self, task_id: int) -> int:
        """Delete all comments for a task. Returns count of deleted comments."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM comment WHERE task_id = $1",
                task_id
            )
            return int(result.split()[-1])

    async def delete_by_user(self, user_id: int) -> int:
        """Delete all comments by a user. Returns count of deleted comments."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM comment WHERE user_id = $1",
                user_id
            )
            return int(result.split()[-1])

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all comments with pagination."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM comment
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def count_by_task(self, task_id: int) -> int:
        """Count comments for a task."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM comment WHERE task_id = $1",
                task_id
            )
            return count

    async def count_by_user(self, user_id: int) -> int:
        """Count comments by a user."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM comment WHERE user_id = $1",
                user_id
            )
            return count

    async def get_recent_for_task(self, task_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent comments for a task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM comment
                WHERE task_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                task_id,
                limit
            )
            return [dict(row) for row in rows]



