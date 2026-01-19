"""Attachment repository for database operations."""

from typing import Optional, List, Dict, Any
import asyncpg
import logging

logger = logging.getLogger(__name__)


class AttachmentRepository:
    """Repository for Attachment entity operations."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize AttachmentRepository.
        
        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool
    
    async def get_by_id(self, attachment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get attachment by ID.
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            Attachment data as dict or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, task_id, filename, content_type, 
                       storage_path, size_bytes, uploaded_at
                FROM attachment
                WHERE id = $1
                """,
                attachment_id
            )
            if row:
                logger.debug(f"Attachment found: ID={attachment_id}")
                return dict(row)
            
            logger.warning(f"Attachment not found: ID={attachment_id}")
            return None
    
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new attachment.
        
        Args:
            data: Attachment data (task_id, filename, content_type, storage_path, size_bytes)
            
        Returns:
            Created attachment data
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO attachment (
                    task_id, filename, content_type, storage_path, size_bytes
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, task_id, filename, content_type, 
                          storage_path, size_bytes, uploaded_at
                """,
                data.get("task_id"),
                data.get("filename"),
                data.get("content_type"),
                data.get("storage_path"),
                data.get("size_bytes"),
            )
            
            logger.info(f"Attachment created: ID={row['id']}, filename='{row['filename']}'")
            return dict(row)
    
    async def delete(self, attachment_id: int) -> bool:
        """
        Delete attachment by ID.
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM attachment WHERE id = $1",
                attachment_id
            )
            
            # result is like "DELETE 1" or "DELETE 0"
            deleted = result.split()[-1] == "1"
            
            if deleted:
                logger.info(f"Attachment deleted: ID={attachment_id}")
            else:
                logger.warning(f"Attachment not found for deletion: ID={attachment_id}")
            
            return deleted
    
    async def get_by_task_id(self, task_id: int) -> List[Dict[str, Any]]:
        """
        Get all attachments for a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of attachments
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, task_id, filename, content_type, 
                       storage_path, size_bytes, uploaded_at
                FROM attachment
                WHERE task_id = $1
                ORDER BY uploaded_at DESC
                """,
                task_id
            )
            return [dict(row) for row in rows]
    
    async def count_by_task_id(self, task_id: int) -> int:
        """
        Count attachments for a specific task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Total count
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM attachment WHERE task_id = $1",
                task_id
            )
            return count or 0
