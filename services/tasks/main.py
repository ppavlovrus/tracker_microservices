"""Main entry point for Tasks Service."""

import asyncio
import asyncpg

from services.tasks.config import (
    DATABASE_URL,
    DB_POOL_MIN_SIZE,
    DB_POOL_MAX_SIZE,
    DB_POOL_COMMAND_TIMEOUT,
    DB_POOL_MAX_QUERIES,
    DB_POOL_MAX_INACTIVE_LIFETIME,
    AMQP_URL,
    QUEUE_NAME,
)
from services.tasks.src.workers import run_worker

# Global database pool
db_pool: asyncpg.Pool = None


async def init_db_pool():
    """Initialize database connection pool."""
    global db_pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        command_timeout=DB_POOL_COMMAND_TIMEOUT,
        max_queries=DB_POOL_MAX_QUERIES,
        max_inactive_connection_lifetime=DB_POOL_MAX_INACTIVE_LIFETIME,
    )
    print("Database connection pool created")
    return db_pool


async def close_db_pool():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        print("Database connection pool closed")


def get_pool() -> asyncpg.Pool:
    """Get database pool instance.
    
    Returns:
        Database connection pool
    """
    return db_pool


async def main():
    """Main function to start Tasks Service."""
    print("Starting Tasks Service...")
    
    try:
        # Initialize database pool
        await init_db_pool()
        
        # Patch get_pool function in common module
        import task_tracker_common.db.pool as pool_module
        pool_module.db_pool = db_pool
        
        # Start worker
        await run_worker(AMQP_URL)
        
    except KeyboardInterrupt:
        print("\nShutting down Tasks Service...")
    except Exception as e:
        print(f"Error starting Tasks Service: {e}")
        raise
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())


