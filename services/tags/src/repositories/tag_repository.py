"""Tag repository."""
from typing import Optional, List, Dict, Any
from task_tracker_common.repository import BaseRepository


class TagRepository(BaseRepository):
    """Repository for Tag entity."""

    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get tag by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tag WHERE id = $1",
                id
            )
            return dict(row) if row else None

    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tag by name."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tag WHERE name = $1",
                name
            )
            return dict(row) if row else None

    async def search_by_name(self, pattern: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search tags by name pattern (case-insensitive)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tag
                WHERE name ILIKE $1
                ORDER BY name
                LIMIT $2
                """,
                f"%{pattern}%",
                limit
            )
            return [dict(row) for row in rows]

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new tag."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO tag (name) VALUES ($1) RETURNING *",
                data["name"]
            )
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update tag."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE tag SET name = $1 WHERE id = $2 RETURNING *",
                data["name"],
                id
            )
            return dict(row) if row else None

    async def delete(self, id: int) -> bool:
        """Delete tag."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM tag WHERE id = $1",
                id
            )
            return int(result.split()[-1]) > 0

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all tags with pagination."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tag
                ORDER BY name
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def get_tags_for_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Get all tags assigned to a specific task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.* FROM tag t
                JOIN task_tag tt ON t.id = tt.tag_id
                WHERE tt.task_id = $1
                ORDER BY t.name
                """,
                task_id
            )
            return [dict(row) for row in rows]

    async def get_popular_tags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most popular tags (by usage count)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.*, COUNT(tt.task_id) as usage_count
                FROM tag t
                LEFT JOIN task_tag tt ON t.id = tt.tag_id
                GROUP BY t.id
                ORDER BY usage_count DESC, t.name
                LIMIT $1
                """,
                limit
            )
            return [dict(row) for row in rows]



