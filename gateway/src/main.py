"""Gateway FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from task_tracker_common.messaging import RabbitMQClient

from .config import AMQP_URL, SERVICE_NAME, HOST, PORT, LOG_LEVEL
from .api.routers import tasks, users

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# RabbitMQ client instance
rabbitmq_client: RabbitMQClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    Manages RabbitMQ connection lifecycle.
    """
    global rabbitmq_client
    
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
        
        # Set client in routers
        tasks.set_rabbitmq_client(rabbitmq_client)
        users.set_rabbitmq_client(rabbitmq_client)
        
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

# Include routers
app.include_router(tasks.router)
app.include_router(users.router)


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