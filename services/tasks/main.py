"""Tasks Service - Worker for handling task commands."""

import asyncio
import logging
import signal
import sys

import asyncpg
from aio_pika import IncomingMessage
from task_tracker_common.messaging import RabbitMQClient

from config import (
    AMQP_URL,
    SERVICE_NAME,
    QUEUE_NAME,
    PREFETCH_COUNT,
    LOG_LEVEL,
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_POOL_MIN_SIZE,
    DB_POOL_MAX_SIZE,
)
from src.repositories import TaskRepository
from src.handlers import TaskHandlers

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
db_pool: asyncpg.Pool = None
rabbitmq_client: RabbitMQClient = None
task_handlers: TaskHandlers = None
shutdown_event = asyncio.Event()


async def create_db_pool() -> asyncpg.Pool:
    """
    Create database connection pool.
    
    Returns:
        asyncpg connection pool
    """
    logger.info("Creating database connection pool...")
    
    dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
    )
    
    logger.info(f"Database pool created: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    return pool


async def handle_command(payload: dict, message: IncomingMessage) -> dict:
    """
    Handle incoming command from RabbitMQ.
    
    Args:
        payload: Command payload
        message: RabbitMQ message
        
    Returns:
        Response dict
    """
    command = payload.get("command")
    data = payload.get("data", {})
    
    logger.debug(f"Handling command: {command}")
    
    try:
        if command == "create_task":
            return await task_handlers.handle_create_task(data)
        
        elif command == "get_task":
            return await task_handlers.handle_get_task(data)
        
        elif command == "update_task":
            return await task_handlers.handle_update_task(data)
        
        elif command == "delete_task":
            return await task_handlers.handle_delete_task(data)
        
        elif command == "list_tasks":
            return await task_handlers.handle_list_tasks(data)
        
        else:
            logger.warning(f"Unknown command: {command}")
            return {
                "success": False,
                "error": f"Unknown command: {command}",
                "error_type": "UnknownCommand"
            }
    
    except Exception as e:
        logger.error(f"Error handling command {command}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


async def startup():
    """Initialize service components."""
    global db_pool, rabbitmq_client, task_handlers
    
    logger.info("=" * 60)
    logger.info(f"Starting {SERVICE_NAME}...")
    logger.info("=" * 60)
    
    try:
        # Create database pool
        db_pool = await create_db_pool()
        
        # Initialize repository and handlers
        task_repository = TaskRepository(db_pool)
        task_handlers = TaskHandlers(task_repository)
        
        logger.info("Repository and handlers initialized")
        
        # Initialize RabbitMQ client
        rabbitmq_client = RabbitMQClient(
            amqp_url=AMQP_URL,
            service_name=SERVICE_NAME
        )
        
        await rabbitmq_client.connect()
        logger.info("Connected to RabbitMQ")
        
        # Setup event publisher (for future use)
        await rabbitmq_client.setup_event_publisher()
        logger.info("Event publisher ready")
        
        # Start consuming commands
        await rabbitmq_client.consume(
            queue_name=QUEUE_NAME,
            callback=handle_command,
            prefetch_count=PREFETCH_COUNT
        )
        
        logger.info("=" * 60)
        logger.info(f"{SERVICE_NAME} started successfully!")
        logger.info(f"Listening to queue: {QUEUE_NAME}")
        logger.info(f"Prefetch count: {PREFETCH_COUNT}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Failed to start {SERVICE_NAME}: {e}", exc_info=True)
        raise


async def shutdown():
    """Cleanup service components."""
    logger.info("=" * 60)
    logger.info(f"Shutting down {SERVICE_NAME}...")
    logger.info("=" * 60)
    
    try:
        # Close RabbitMQ connection
        if rabbitmq_client:
            await rabbitmq_client.close()
            logger.info("RabbitMQ connection closed")
        
        # Close database pool
        if db_pool:
            await db_pool.close()
            logger.info("Database pool closed")
        
        logger.info(f"{SERVICE_NAME} stopped successfully")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {sig}, initiating shutdown...")
    shutdown_event.set()


async def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Startup
        await startup()
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        # Cleanup
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
