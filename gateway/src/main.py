"""Gateway FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from task_tracker_common.messaging import RabbitMQClient

from .config import (
    AMQP_URL,
    SERVICE_NAME,
    HOST,
    PORT,
    LOG_LEVEL,
    REDIS_URL,
    CACHE_ENABLED,
)
from .cache import Cache
from .api.routers import tasks, users, web, comments, tags, attachments

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# RabbitMQ client instance
rabbitmq_client: RabbitMQClient = None

# Redis cache instance
cache: Cache = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    Manages RabbitMQ connection lifecycle.
    """
    global rabbitmq_client, cache

    # Startup
    logger.info("Starting Gateway service...")

    try:
        # Initialize RabbitMQ client
        rabbitmq_client = RabbitMQClient(
            amqp_url=AMQP_URL,
            service_name=SERVICE_NAME
        )

        # Connect and setup RPC client
        await rabbitmq_client.connect()
        await rabbitmq_client.setup_rpc_client()

        # Initialize Redis cache (best-effort, never blocks startup)
        cache = Cache(redis_url=REDIS_URL, enabled=CACHE_ENABLED)
        await cache.connect()

        # Set client in routers
        tasks.set_rabbitmq_client(rabbitmq_client)
        users.set_rabbitmq_client(rabbitmq_client)
        comments.set_rabbitmq_client(rabbitmq_client)
        tags.set_rabbitmq_client(rabbitmq_client)
        attachments.set_rabbitmq_client(rabbitmq_client)

        # Wire cache into the routers that use it
        tasks.set_cache(cache)
        tags.set_cache(cache)

        logger.info("Gateway service started successfully")
        logger.info(f"RabbitMQ: {AMQP_URL}")
        
    except Exception as e:
        logger.error(f"Failed to start Gateway: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Gateway service...")
    
    try:
        if rabbitmq_client:
            await rabbitmq_client.close()
        if cache:
            await cache.close()
        logger.info("Gateway service stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="Task Tracker Gateway",
    description="API Gateway for Task Tracker microservices",
    version="0.1.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(web.router)
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(comments.router)
app.include_router(tags.router)
app.include_router(attachments.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "rabbitmq_connected": rabbitmq_client is not None
    }


# Application entry point
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level=LOG_LEVEL.lower()
    )