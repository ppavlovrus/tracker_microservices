"""Task repository for database operations."""

from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
import logging

logger = logging.getLogger(__name__)


class TaskRepository:
    """Repository for Task entity operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize TaskRepository.
        
        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool
    
    async def get_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """
        Get task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, status_id, creator_id,
                       deadline_start, deadline_end, created_at, updated_at
                FROM task
                WHERE id = $1
                """,
                task_id
            )
            return dict(row) if row else None
    
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new task.
        
        Args:
            data: Task data (title, description, creator_id, status_id, deadlines)
            
        Returns:
            Created task data
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO task (
                    title, description, status_id, creator_id,
                    deadline_start, deadline_end
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, title, description, status_id, creator_id,
                          deadline_start, deadline_end, created_at, updated_at
                """,
                data.get("title"),
                data.get("description"),
                data.get("status_id", 1),  # Default status
                data.get("creator_id"),
                data.get("deadline_start"),
                data.get("deadline_end"),
            )
            
            logger.info(f"Task created: ID={row['id']}, title='{row['title']}'")
            return dict(row)
    
    async def update(self, task_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update task by ID.
        
        Args:
            task_id: Task ID
            data: Fields to update
            
        Returns:
            Updated task data or None if not found
        """
        # Build dynamic UPDATE query for provided fields only
        set_clauses = []
        values = []
        param_index = 1
        
        for field in ["title", "description", "status_id", "deadline_start", "deadline_end"]:
            if field in data:
                set_clauses.append(f"{field} = ${param_index}")
                values.append(data[field])
                param_index += 1
        
        if not set_clauses:
            # No fields to update, just return current task
            return await self.get_by_id(task_id)
        
        # Add updated_at
        set_clauses.append(f"updated_at = ${param_index}")
        values.append(datetime.utcnow())
        param_index += 1
        
        # Add task_id for WHERE clause
        values.append(task_id)
        
        query = f"""
            UPDATE task
            SET {', '.join(set_clauses)}
            WHERE id = ${param_index}
            RETURNING id, title, description, status_id, creator_id,
                      deadline_start, deadline_end, created_at, updated_at
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            
            if row:
                logger.info(f"Task updated: ID={task_id}")
                return dict(row)
            
            logger.warning(f"Task not found for update: ID={task_id}")
            return None
    
    async def delete(self, task_id: int) -> bool:
        """
        Delete task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM task WHERE id = $1",
                task_id
            )
            
            # result is like "DELETE 1" or "DELETE 0"
            deleted = result.split()[-1] == "1"
            
            if deleted:
                logger.info(f"Task deleted: ID={task_id}")
            else:
                logger.warning(f"Task not found for deletion: ID={task_id}")
            
            return deleted
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all tasks with pagination.
        
        Args:
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip
            
        Returns:
            List of tasks
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, description, status_id, creator_id,
                       deadline_start, deadline_end, created_at, updated_at
                FROM task
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )
            return [dict(row) for row in rows]
    
    async def count_all(self) -> int:
        """
        Count total number of tasks.
        
        Returns:
            Total count
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM task")
            return count or 0
