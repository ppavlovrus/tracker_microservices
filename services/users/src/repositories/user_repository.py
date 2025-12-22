from typing import Optional, List, Dict, Any
from task_tracker_common.repository import BaseRepository

class UserRepository(BaseRepository):
    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM \"user\" WHERE id = $1",
                id
            )
            return dict(row) if row else None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM \"user\" WHERE email = $1",
                email
            )
            return dict(row) if row else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new user."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO "user" (username, email, password_hash)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                data["username"],
                data["email"],
                data["password_hash"]
            )
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user."""
        async with self.pool.acquire() as conn:
            # Build dynamic UPDATE query based on provided fields
            fields = []
            values = []
            idx = 1

            for key, value in data.items():
                fields.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

            values.append(id)

            query = f"""
                   UPDATE "user"
                   SET {', '.join(fields)}
                   WHERE id = ${idx}
                   RETURNING *
               """

            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None

    async def delete(self, id: int) -> bool:
        """Delete user."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM \"user\" WHERE id = $1",
                id
            )
            # result format: "DELETE N" where N is count
            return int(result.split()[-1]) > 0

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all users with pagination."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM "user"
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]