"""User repository for database operations."""

from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
import logging

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for User entity operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize UserRepository.
        
        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool
    
    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.
        
        Args:
            id: User ID
            
        Returns:
            User data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash, 
                       created_at, updated_at
                FROM "user"
                WHERE id = $1
                """,
                id
            )
            if row:
                logger.debug(f"User found: ID={id}")
                return dict(row)
            
            logger.warning(f"User not found: ID={id}")
            return None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email.
        
        Args:
            email: User email
            
        Returns:
            User data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, password_hash,
                       created_at, updated_at
                FROM "user"
                WHERE email = $1
                """,
                email
            )
            if row:
                logger.debug(f"User found by email: {email}")
                return dict(row)
            
            return None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new user.
        
        Args:
            data: User data (username, email, password_hash)
            
        Returns:
            Created user data
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO "user" (username, email, password_hash)
                VALUES ($1, $2, $3)
                RETURNING id, username, email, password_hash,
                          created_at, updated_at
                """,
                data["username"],
                data["email"],
                data["password_hash"]
            )
            
            logger.info(f"User created: ID={row['id']}, username='{row['username']}'")
            return dict(row)

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update user by ID.
        
        Args:
            id: User ID
            data: Fields to update
            
        Returns:
            Updated user data or None if not found
        """
        # Build dynamic UPDATE query for provided fields only
        set_clauses = []
        values = []
        param_index = 1
        
        for field in ["username", "email", "password_hash"]:
            if field in data:
                set_clauses.append(f"{field} = ${param_index}")
                values.append(data[field])
                param_index += 1
        
        if not set_clauses:
            # No fields to update, just return current user
            return await self.get_by_id(id)
        
        # Add updated_at
        set_clauses.append(f"updated_at = ${param_index}")
        values.append(datetime.utcnow())
        param_index += 1
        
        # Add id for WHERE clause
        values.append(id)
        
        query = f"""
            UPDATE "user"
            SET {', '.join(set_clauses)}
            WHERE id = ${param_index}
            RETURNING id, username, email, password_hash,
                      created_at, updated_at
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            
            if row:
                logger.info(f"User updated: ID={id}")
                return dict(row)
            
            logger.warning(f"User not found for update: ID={id}")
            return None

    async def delete(self, id: int) -> bool:
        """
        Delete user by ID.
        
        Args:
            id: User ID
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM \"user\" WHERE id = $1",
                id
            )
            
            # result is like "DELETE 1" or "DELETE 0"
            deleted = result.split()[-1] == "1"
            
            if deleted:
                logger.info(f"User deleted: ID={id}")
            else:
                logger.warning(f"User not found for deletion: ID={id}")
            
            return deleted

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all users with pagination.
        
        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            
        Returns:
            List of users
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, username, email, password_hash,
                       created_at, updated_at
                FROM "user"
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]
    
    async def count_all(self) -> int:
        """
        Count total number of users.
        
        Returns:
            Total count
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM \"user\"")
            return count or 0