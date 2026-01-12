"""Database connection pool management."""
import asyncpg
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from config import (
    DATABASE_URL,
    DB_POOL_MIN_SIZE,
    DB_POOL_MAX_SIZE,
    DB_POOL_COMMAND_TIMEOUT,
    DB_POOL_MAX_QUERIES,
    DB_POOL_MAX_INACTIVE_LIFETIME,
)

# Global connection pool
db_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database connection pool lifecycle.

    Creates connection pool on startup and closes it on shutdown.
    This ensures efficient connection reuse across requests.

    Args:
        app: FastAPI application instance
    """
    global db_pool

    # Startup: create connection pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        command_timeout=DB_POOL_COMMAND_TIMEOUT,
        max_queries=DB_POOL_MAX_QUERIES,
        max_inactive_connection_lifetime=DB_POOL_MAX_INACTIVE_LIFETIME,
    )
    print("Database connection pool created")

    yield

    # Shutdown: close connection pool
    await db_pool.close()
    print("Database connection pool closed")


def get_pool() -> Optional[asyncpg.Pool]:
    """Get database connection pool.

    Returns:
        Database connection pool or None if not initialized
    """
    return db_pool
