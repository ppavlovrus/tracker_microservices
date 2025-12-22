"""Task repository."""
from typing import Optional, List, Dict, Any
from datetime import date
from task_tracker_common.repository import BaseRepository


class TaskRepository(BaseRepository):
    """Repository for Task entity."""

    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM task WHERE id = $1",
                id
            )
            return dict(row) if row else None

    async def get_by_creator(self, creator_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get tasks created by specific user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM task
                WHERE creator_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                creator_id,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def get_by_status(self, status_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get tasks by status."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM task
                WHERE status_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status_id,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def get_assigned_to_user(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get tasks assigned to specific user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.* FROM task t
                JOIN task_assignee ta ON t.id = ta.task_id
                WHERE ta.user_id = $1
                ORDER BY t.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new task."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO task (title, description, status_id, creator_id, deadline_start, deadline_end)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                data["title"],
                data.get("description"),
                data["status_id"],
                data["creator_id"],
                data.get("deadline_start"),
                data.get("deadline_end")
            )
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update task."""
        async with self.pool.acquire() as conn:
            fields = []
            values = []
            idx = 1

            for key, value in data.items():
                fields.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

            # Always update updated_at
            fields.append(f"updated_at = NOW()")
            values.append(id)

            query = f"""
                UPDATE task
                SET {', '.join(fields)}
                WHERE id = ${idx}
                RETURNING *
            """

            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None

    async def delete(self, id: int) -> bool:
        """Delete task."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM task WHERE id = $1",
                id
            )
            return int(result.split()[-1]) > 0

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all tasks with pagination."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM task
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    # Task assignees management

    async def assign_users(self, task_id: int, user_ids: List[int]) -> bool:
        """Assign multiple users to task (replaces existing assignments)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Remove existing assignments
                await conn.execute(
                    "DELETE FROM task_assignee WHERE task_id = $1",
                    task_id
                )
                
                # Add new assignments
                if user_ids:
                    await conn.executemany(
                        "INSERT INTO task_assignee (task_id, user_id) VALUES ($1, $2)",
                        [(task_id, user_id) for user_id in user_ids]
                    )
                
                # Update task updated_at
                await conn.execute(
                    "UPDATE task SET updated_at = NOW() WHERE id = $1",
                    task_id
                )
                
                return True

    async def add_assignee(self, task_id: int, user_id: int) -> bool:
        """Add single user to task assignees."""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO task_assignee (task_id, user_id) VALUES ($1, $2)",
                    task_id,
                    user_id
                )
                await conn.execute(
                    "UPDATE task SET updated_at = NOW() WHERE id = $1",
                    task_id
                )
                return True
            except Exception:  # Duplicate or constraint violation
                return False

    async def remove_assignee(self, task_id: int, user_id: int) -> bool:
        """Remove user from task assignees."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM task_assignee WHERE task_id = $1 AND user_id = $2",
                task_id,
                user_id
            )
            if int(result.split()[-1]) > 0:
                await conn.execute(
                    "UPDATE task SET updated_at = NOW() WHERE id = $1",
                    task_id
                )
                return True
            return False

    async def get_assignees(self, task_id: int) -> List[int]:
        """Get list of user IDs assigned to task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM task_assignee WHERE task_id = $1",
                task_id
            )
            return [row["user_id"] for row in rows]

    # Task tags management

    async def assign_tags(self, task_id: int, tag_ids: List[int]) -> bool:
        """Assign multiple tags to task (replaces existing tags)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Remove existing tags
                await conn.execute(
                    "DELETE FROM task_tag WHERE task_id = $1",
                    task_id
                )
                
                # Add new tags
                if tag_ids:
                    await conn.executemany(
                        "INSERT INTO task_tag (task_id, tag_id) VALUES ($1, $2)",
                        [(task_id, tag_id) for tag_id in tag_ids]
                    )
                
                # Update task updated_at
                await conn.execute(
                    "UPDATE task SET updated_at = NOW() WHERE id = $1",
                    task_id
                )
                
                return True

    async def add_tag(self, task_id: int, tag_id: int) -> bool:
        """Add single tag to task."""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO task_tag (task_id, tag_id) VALUES ($1, $2)",
                    task_id,
                    tag_id
                )
                await conn.execute(
                    "UPDATE task SET updated_at = NOW() WHERE id = $1",
                    task_id
                )
                return True
            except Exception:  # Duplicate or constraint violation
                return False

    async def remove_tag(self, task_id: int, tag_id: int) -> bool:
        """Remove tag from task."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM task_tag WHERE task_id = $1 AND tag_id = $2",
                task_id,
                tag_id
            )
            if int(result.split()[-1]) > 0:
                await conn.execute(
                    "UPDATE task SET updated_at = NOW() WHERE id = $1",
                    task_id
                )
                return True
            return False

    async def get_tags(self, task_id: int) -> List[int]:
        """Get list of tag IDs for task."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tag_id FROM task_tag WHERE task_id = $1",
                task_id
            )
            return [row["tag_id"] for row in rows]


class TaskStatusRepository(BaseRepository):
    """Repository for TaskStatus entity."""

    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get status by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM task_status WHERE id = $1",
                id
            )
            return dict(row) if row else None

    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get status by name."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM task_status WHERE name = $1",
                name
            )
            return dict(row) if row else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new status."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO task_status (name) VALUES ($1) RETURNING *",
                data["name"]
            )
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update status."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE task_status SET name = $1 WHERE id = $2 RETURNING *",
                data["name"],
                id
            )
            return dict(row) if row else None

    async def delete(self, id: int) -> bool:
        """Delete status."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM task_status WHERE id = $1",
                id
            )
            return int(result.split()[-1]) > 0

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all statuses."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM task_status ORDER BY id"
            )
            return [dict(row) for row in rows]

