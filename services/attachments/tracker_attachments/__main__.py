"""Attachments Service - Worker for handling attachment commands."""

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
from aio_pika import IncomingMessage
from pydantic import BaseModel, ValidationError
from task_tracker_common.contracts.commands import (
    AttachmentCommand,
    AttachmentCreationContract,
    AttachmentDeleteContract,
    AttachmentGetByIdContract,
    AttachmentListByTaskContract,
)
from task_tracker_common.contracts.responses import ErrorCode, rpc_error
from task_tracker_common.messaging import RabbitMQClient
from task_tracker_common.observability import setup_telemetry, shutdown_telemetry

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
    OTEL_SERVICE_NAME,
    PREFETCH_COUNT,
    QUEUE_NAME,
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_ENDPOINT_INTERNAL,
    S3_ENDPOINT_PUBLIC,
    S3_PRESIGN_EXPIRE,
    S3_REGION,
    S3_SECRET_KEY,
    SERVICE_NAME,
)
from .handlers import AttachmentHandlers
from .repositories import AttachmentRepository
from .storage import S3Storage

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global instances
db_pool: asyncpg.Pool = None
rabbitmq_client: RabbitMQClient = None
shutdown_event = None

# Command name -> (payload contract, handler). Filled in at startup, once the
# handlers exist.
Handler = Callable[[BaseModel], Awaitable[dict[str, Any]]]
command_table: dict[str, tuple[type[BaseModel], Handler]] = {}


def build_command_table(handlers: AttachmentHandlers) -> dict[str, tuple[type[BaseModel], Handler]]:
    """Map every command this service answers to its payload contract.

    A table rather than an if/elif ladder: adding a command means adding a row,
    the enum keeps the names from drifting apart between the two sides of the
    bus, and every payload passes through a contract before a handler sees it,
    in one place instead of four.
    """
    return {
        AttachmentCommand.CREATE: (AttachmentCreationContract, handlers.handle_create_attachment),
        AttachmentCommand.GET: (AttachmentGetByIdContract, handlers.handle_get_attachment),
        AttachmentCommand.DELETE: (AttachmentDeleteContract, handlers.handle_delete_attachment),
        AttachmentCommand.LIST: (AttachmentListByTaskContract, handlers.handle_list_attachments_by_task),
    }


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
    """Validate an incoming command and route it to its handler.

    Three failures are told apart here, and each gets its own code, because the
    caller has to react to them differently: a command this service does not
    answer, a payload that does not satisfy the contract, and a handler that
    blew up.
    """
    command = payload.get("command")
    data = payload.get("data", {})

    entry = command_table.get(command)
    if entry is None:
        logger.warning(f"Unknown command: {command}")
        return rpc_error(ErrorCode.VALIDATION_ERROR, f"Unknown command: {command}", "UnknownCommand")

    contract, handler = entry

    try:
        request = contract.model_validate(data)
    except ValidationError as e:
        # The violations go to the log, not onto the bus: a payload that fails
        # the contract is a bug in whoever sent it, and the field paths would
        # otherwise ride all the way out to an HTTP client.
        logger.warning(f"Rejected {command}: {e}")
        return rpc_error(ErrorCode.VALIDATION_ERROR, f"{e.error_count()} contract violation(s)", "ValidationError")

    logger.debug(f"Handling command: {command}")

    try:
        return await handler(request)
    except Exception as e:
        # str(e) rides the bus on purpose: the gateway decides what the client
        # is told, and this half is for its log.
        logger.error(f"Error handling command {command}: {e}", exc_info=True)
        return rpc_error(ErrorCode.INTERNAL, str(e), type(e).__name__)


async def startup():
    """Initialize service components."""
    global db_pool, rabbitmq_client

    # First, before the pool is created: the asyncpg wrapper must be in
    # place before the pool captures the connect callable, or no query of
    # this process would ever be traced.
    setup_telemetry(OTEL_SERVICE_NAME, instrument_db=True)

    logger.info("=" * 60)
    logger.info(f"Starting {SERVICE_NAME}...")
    logger.info("=" * 60)

    try:
        # Create database pool
        db_pool = await create_db_pool()

        # Initialize object storage and ensure the bucket exists
        storage = S3Storage(
            internal_endpoint=S3_ENDPOINT_INTERNAL,
            public_endpoint=S3_ENDPOINT_PUBLIC,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            bucket=S3_BUCKET,
            region=S3_REGION,
            presign_expire=S3_PRESIGN_EXPIRE,
        )
        await storage.ensure_bucket()

        # Initialize repository and handlers
        attachment_repository = AttachmentRepository(db_pool)
        attachment_handlers = AttachmentHandlers(attachment_repository, storage)
        command_table.update(build_command_table(attachment_handlers))

        logger.info(f"Repository and handlers initialized ({len(command_table)} commands)")

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

    finally:
        # Last, after every client that could still produce a span is gone --
        # and even when one of the closes above failed, because those are
        # exactly the runs whose buffered spans nobody gets a second look at.
        shutdown_telemetry()


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
