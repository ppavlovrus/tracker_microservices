"""Base repository interfaces for Task Tracker microservices."""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import asyncpg


class BaseRepository(ABC):
    """Base repository interface.

    Simple abstract class that defines common interfaces for repositories.
    Each microservice implements its own repositories using asyncpg directly.
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize repository with connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """Get entity by ID.

        Args:
            id: Entity ID

        Returns:
            Entity dict or None if not found
        """
        pass

    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new entity.

        Args:
            data: Entity data

        Returns:
            Created entity dict
        """
        pass

    @abstractmethod
    async def update(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update entity.

        Args:
            id: Entity ID
            data: Updated data

        Returns:
            Updated entity dict or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Delete entity.

        Args:
            id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all entities with pagination.

        Args:
            limit: Maximum number of items (default: 100)
            offset: Number of items to skip (default: 0)

        Returns:
            List of entity dicts
        """
        pass
