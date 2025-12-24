from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from gateway.src.config import AMQP_URL, RPC_TIMEOUT, GATEWAY_HOST, GATEWAY_PORT
from gateway.src.messaging import GatewayMessagingClient

# Global messaging client
messaging_client: Optional[GatewayMessagingClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Gateway service lifecycle."""
    global messaging_client
    
    # Startup: Connect to RabbitMQ
    messaging_client = GatewayMessagingClient(AMQP_URL, RPC_TIMEOUT)
    await messaging_client.connect()
    print("Gateway service started")
    
    yield
    
    # Shutdown: Close RabbitMQ connection
    if messaging_client:
        await messaging_client.close()
    print("Gateway service stopped")


app = FastAPI(
    title="Task Tracker Gateway",
    description="API Gateway for Task Tracker microservices",
    version="0.1.0",
    lifespan=lifespan
)


def get_messaging_client() -> GatewayMessagingClient:
    """Get messaging client instance.
    
    Returns:
        Gateway messaging client
        
    Raises:
        RuntimeError: If client not initialized
    """
    if messaging_client is None:
        raise RuntimeError("Messaging client not initialized")
    return messaging_client


# Import routers
from gateway.src.api.routers import tasks

# Include routers
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
# app.include_router(users.router, prefix="/users", tags=["Users"])
# app.include_router(tags.router, prefix="/tags", tags=["Tags"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Task Tracker Gateway",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Application entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "gateway.src.main:app",
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        reload=True
    )