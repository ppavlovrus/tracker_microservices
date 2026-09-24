"""Comments Service - Worker for handling comment commands."""

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable

import asyncpg
from aio_pika import IncomingMessage
from task_tracker_common.contracts.responses import ErrorCode, rpc_error
from task_tracker_common.messaging import RabbitMQClient

from .config import (
    AMQP_URL,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_POOL_MAX_SIZE,
    DB_POOL_MIN_SIZE,
    DB_PORT,
    DB_USER,
    LOG_LEVEL,
    PREFETCH_COUNT,
    QUEUE_NAME,
    SERVICE_NAME,
)
from .handlers import CommentHandlers
from .repositories import CommentRepository

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# One command handler: takes the command payload, answers with a response dict.
CommandHandler = Callable[[dict], Awaitable[dict]]

# Global instances
db_pool: asyncpg.Pool = None
rabbitmq_client: RabbitMQClient = None
comment_handlers: CommentHandlers = None
shutdown_event = None

# Command name -> handler, filled by startup() once the handlers exist.
dispatch: dict[str, CommandHandler] = {}


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


def build_dispatch(handlers: CommentHandlers) -> dict[str, CommandHandler]:
    """Map every command name on the wire to the coroutine that answers it.

    A table rather than an if/elif ladder: a new command is one line, and the
    dispatcher below stays flat no matter how many there are. Built once at
    startup, when the handlers exist.
    """
    return {
        "create_comment": handlers.handle_create_comment,
        "get_comment": handlers.handle_get_comment,
        "update_comment": handlers.handle_update_comment,
        "delete_comment": handlers.handle_delete_comment,
        "list_comments_by_task": handlers.handle_list_comments_by_task,
    }


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

    handler = dispatch.get(command)
    if handler is None:
        logger.warning(f"Unknown command: {command}")
        return {"success": False, "error": f"Unknown command: {command}", "error_type": "UnknownCommand"}

    try:
        return await handler(data)
    except Exception as e:
        # str(e) stays in the log: an unclassified failure is often a driver
        # message naming a table, a constraint and the offending value, and
        # that is not something an HTTP client should be handed.
        logger.error(f"Error handling command {command}: {e}", exc_info=True)
        return rpc_error(ErrorCode.INTERNAL, "Internal error", type(e).__name__)


async def startup():
    """Initialize service components."""
    global db_pool, rabbitmq_client, comment_handlers, dispatch

    logger.info("=" * 60)
    logger.info(f"Starting {SERVICE_NAME}...")
    logger.info("=" * 60)

    try:
        # Create database pool
        db_pool = await create_db_pool()

        # Initialize repository and handlers
        comment_repository = CommentRepository(db_pool)
        comment_handlers = CommentHandlers(comment_repository)
        dispatch = build_dispatch(comment_handlers)

        logger.info("Repository and handlers initialized")

        # Initialize RabbitMQ client
        rabbitmq_client = RabbitMQClient(amqp_url=AMQP_URL, service_name=SERVICE_NAME)

        await rabbitmq_client.connect()
        logger.info("Connected to RabbitMQ")

        # Setup event publisher (for future use)
        await rabbitmq_client.setup_event_publisher()
        logger.info("Event publisher ready")

        # Start consuming commands
        await rabbitmq_client.consume(queue_name=QUEUE_NAME, callback=handle_command, prefetch_count=PREFETCH_COUNT)

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
        # Stop taking new messages and let the ones in flight finish before
        # the connection and the pool they are using go away.
        if rabbitmq_client:
            await rabbitmq_client.stop_consuming()
            await rabbitmq_client.close()
            logger.info("RabbitMQ connection closed")

        # Close database pool
        if db_pool:
            await db_pool.close()
            logger.info("Database pool closed")

        logger.info(f"{SERVICE_NAME} stopped successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


async def main():
    """Main entry point."""
    global shutdown_event

    # Create shutdown event in the current loop
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig}, initiating shutdown...")
        shutdown_event.set()

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
