"""Tag repository for database operations."""

from typing import Optional, List, Dict, Any
import asyncpg
import logging

logger = logging.getLogger(__name__)


class TagRepository:
    """Repository for Tag entity operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize TagRepository.
        
        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool
    
    async def get_by_id(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """
        Get tag by ID.
        
        Args:
            tag_id: Tag ID
            
        Returns:
            Tag data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name
                FROM tag
                WHERE id = $1
                """,
                tag_id
            )
            if row:
                logger.debug(f"Tag found: ID={tag_id}")
                return dict(row)
            
            logger.warning(f"Tag not found: ID={tag_id}")
            return None
    
    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get tag by name.
        
        Args:
            name: Tag name
            
        Returns:
            Tag data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name
                FROM tag
                WHERE name = $1
                """,
                name
            )
            if row:
                logger.debug(f"Tag found by name: {name}")
                return dict(row)
            
            return None
    
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new tag.
        
        Args:
            data: Tag data (name)
            
        Returns:
            Created tag data
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tag (name)
                VALUES ($1)
                RETURNING id, name
                """,
                data.get("name"),
            )
            
            logger.info(f"Tag created: ID={row['id']}, name='{row['name']}'")
            return dict(row)
    
    async def update(self, tag_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update tag by ID.
        
        Args:
            tag_id: Tag ID
            data: Fields to update (name)
            
        Returns:
            Updated tag data or None if not found
        """
        name = data.get("name")
        
        if not name:
            # No name to update, just return current tag
            return await self.get_by_id(tag_id)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE tag
                SET name = $1
                WHERE id = $2
                RETURNING id, name
                """,
                name,
                tag_id
            )
            
            if row:
                logger.info(f"Tag updated: ID={tag_id}")
                return dict(row)
            
            logger.warning(f"Tag not found for update: ID={tag_id}")
            return None
    
    async def delete(self, tag_id: int) -> bool:
        """
        Delete tag by ID.
        
        Args:
            tag_id: Tag ID
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM tag WHERE id = $1",
                tag_id
            )
            
            # result is like "DELETE 1" or "DELETE 0"
            deleted = result.split()[-1] == "1"
            
            if deleted:
                logger.info(f"Tag deleted: ID={tag_id}")
            else:
                logger.warning(f"Tag not found for deletion: ID={tag_id}")
            
            return deleted
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all tags with pagination.
        
        Args:
            limit: Maximum number of tags to return
            offset: Number of tags to skip
            
        Returns:
            List of tags
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name
                FROM tag
                ORDER BY name ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]
    
    async def count_all(self) -> int:
        """
        Count total number of tags.
        
        Returns:
            Total count
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM tag")
            return count or 0
