"""Gateway FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_REFILL_RATE,
    METRICS_ENABLED,
)
from .cache import Cache
from .ratelimit import RateLimiter
from .metrics import build_instrumentator
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

# Redis-backed rate limiter instance
rate_limiter: RateLimiter = None

# Paths that bypass rate limiting (health checks, docs, metrics, static assets)
RATE_LIMIT_EXEMPT = ("/health", "/docs", "/redoc", "/openapi.json", "/metrics")


def _is_rate_limit_exempt(path: str) -> bool:
    """Return True for paths that should never be rate limited."""
    return path.startswith("/static") or path in RATE_LIMIT_EXEMPT


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    Manages RabbitMQ connection lifecycle.
    """
    global rabbitmq_client, cache, rate_limiter

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

        # Initialize rate limiter (best-effort, fails open)
        rate_limiter = RateLimiter(
            redis_url=REDIS_URL,
            capacity=RATE_LIMIT_CAPACITY,
            refill_rate=RATE_LIMIT_REFILL_RATE,
            enabled=RATE_LIMIT_ENABLED,
        )
        await rate_limiter.connect()

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
        if rate_limiter:
            await rate_limiter.close()
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


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Per-IP token-bucket rate limiting. Fails open if Redis is unavailable."""
    if rate_limiter is None or _is_rate_limit_exempt(request.url.path):
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    allowed, remaining, retry_after = await rate_limiter.check(ip)

    if not allowed:
        logger.warning(f"Rate limit exceeded for {ip} on {request.url.path}")
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(max(1, int(retry_after) + 1)),
                "X-RateLimit-Limit": str(rate_limiter.capacity),
                "X-RateLimit-Remaining": "0",
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(rate_limiter.capacity)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(web.router)
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(comments.router)
app.include_router(tags.router)
app.include_router(attachments.router)

# Expose Prometheus metrics at /metrics. Instrumentation is wired last so its
# middleware sits outermost and times every request -- including the 429s
# produced by the rate-limit middleware above.
if METRICS_ENABLED:
    build_instrumentator().instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )


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