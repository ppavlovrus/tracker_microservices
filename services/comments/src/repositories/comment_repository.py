"""Comment repository for database operations."""

from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
import logging

logger = logging.getLogger(__name__)


class CommentRepository:
    """Repository for Comment entity operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize CommentRepository.
        
        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool
    
    async def get_by_id(self, comment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get comment by ID.
        
        Args:
            comment_id: Comment ID
            
        Returns:
            Comment data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, task_id, user_id, content, 
                       created_at, updated_at
                FROM comment
                WHERE id = $1
                """,
                comment_id
            )
            if row:
                logger.debug(f"Comment found: ID={comment_id}")
                return dict(row)
            
            logger.warning(f"Comment not found: ID={comment_id}")
            return None
    
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new comment.
        
        Args:
            data: Comment data (task_id, user_id, content)
            
        Returns:
            Created comment data
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO comment (task_id, user_id, content)
                VALUES ($1, $2, $3)
                RETURNING id, task_id, user_id, content, 
                          created_at, updated_at
                """,
                data.get("task_id"),
                data.get("user_id"),
                data.get("content"),
            )
            
            logger.info(f"Comment created: ID={row['id']} for task_id={row['task_id']}")
            return dict(row)
    
    async def update(self, comment_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update comment by ID.
        
        Args:
            comment_id: Comment ID
            data: Fields to update (content)
            
        Returns:
            Updated comment data or None if not found
        """
        # For comments we typically only update content
        content = data.get("content")
        
        if not content:
            # No content to update, just return current comment
            return await self.get_by_id(comment_id)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE comment
                SET content = $1, updated_at = $2
                WHERE id = $3
                RETURNING id, task_id, user_id, content, 
                          created_at, updated_at
                """,
                content,
                datetime.utcnow(),
                comment_id
            )
            
            if row:
                logger.info(f"Comment updated: ID={comment_id}")
                return dict(row)
            
            logger.warning(f"Comment not found for update: ID={comment_id}")
            return None
    
    async def delete(self, comment_id: int) -> bool:
        """
        Delete comment by ID.
        
        Args:
            comment_id: Comment ID
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM comment WHERE id = $1",
                comment_id
            )
            
            # result is like "DELETE 1" or "DELETE 0"
            deleted = result.split()[-1] == "1"
            
            if deleted:
                logger.info(f"Comment deleted: ID={comment_id}")
            else:
                logger.warning(f"Comment not found for deletion: ID={comment_id}")
            
            return deleted
    
    async def get_by_task_id(self, task_id: int) -> List[Dict[str, Any]]:
        """
        Get all comments for a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of comments
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, task_id, user_id, content, 
                       created_at, updated_at
                FROM comment
                WHERE task_id = $1
                ORDER BY created_at ASC
                """,
                task_id
            )
            return [dict(row) for row in rows]
    
    async def count_by_task_id(self, task_id: int) -> int:
        """
        Count comments for a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Total count
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM comment WHERE task_id = $1",
                task_id
            )
            return count or 0
