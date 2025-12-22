"""Auth repository."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from task_tracker_common.repository import BaseRepository


class AuthSessionRepository(BaseRepository):
    """Repository for AuthSession entity."""

    async def get_by_id(self, id: UUID | str) -> Optional[Dict[str, Any]]:
        """Get session by ID (UUID)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM auth_session WHERE id = $1",
                id if isinstance(id, UUID) else UUID(id)
            )
            return dict(row) if row else None

    async def get_by_user(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all sessions for a specific user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM auth_session
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def get_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get active (non-expired) sessions for a user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM auth_session
                WHERE user_id = $1 AND expires_at > NOW()
                ORDER BY created_at DESC
                """,
                user_id
            )
            return [dict(row) for row in rows]

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new auth session."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO auth_session (user_id, ip_address, user_agent, expires_at)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                data["user_id"],
                data.get("ip_address"),
                data.get("user_agent"),
                data["expires_at"]
            )
            return dict(row)

    async def update(self, id: UUID | str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update session (mainly for extending expiration)."""
        async with self.pool.acquire() as conn:
            fields = []
            values = []
            idx = 1

            for key, value in data.items():
                fields.append(f"{key} = ${idx}")
                values.append(value)
                idx += 1

            values.append(id if isinstance(id, UUID) else UUID(id))

            query = f"""
                UPDATE auth_session
                SET {', '.join(fields)}
                WHERE id = ${idx}
                RETURNING *
            """

            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None

    async def delete(self, id: UUID | str) -> bool:
        """Delete session (logout)."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM auth_session WHERE id = $1",
                id if isinstance(id, UUID) else UUID(id)
            )
            return int(result.split()[-1]) > 0

    async def delete_by_user(self, user_id: int) -> int:
        """Delete all sessions for a user. Returns count of deleted sessions."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM auth_session WHERE user_id = $1",
                user_id
            )
            return int(result.split()[-1])

    async def delete_expired(self) -> int:
        """Delete all expired sessions. Returns count of deleted sessions."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM auth_session WHERE expires_at < NOW()"
            )
            return int(result.split()[-1])

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all sessions with pagination."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM auth_session
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]

    async def is_valid(self, session_id: UUID | str) -> bool:
        """Check if session exists and is not expired."""
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM auth_session
                    WHERE id = $1 AND expires_at > NOW()
                )
                """,
                session_id if isinstance(session_id, UUID) else UUID(session_id)
            )
            return exists

    async def extend_expiration(self, session_id: UUID | str, new_expires_at: datetime) -> bool:
        """Extend session expiration time."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE auth_session
                SET expires_at = $1
                WHERE id = $2 AND expires_at > NOW()
                """,
                new_expires_at,
                session_id if isinstance(session_id, UUID) else UUID(session_id)
            )
            return int(result.split()[-1]) > 0

    async def count_active_sessions(self, user_id: int) -> int:
        """Count active sessions for a user."""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM auth_session
                WHERE user_id = $1 AND expires_at > NOW()
                """,
                user_id
            )
            return count

