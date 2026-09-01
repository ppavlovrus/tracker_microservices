"""Gateway FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from task_tracker_common.messaging import RabbitMQClient

from .api.errors import register_error_handlers
from .api.routers import (
    attachments,
    auth,
    chat,
    comments,
    oauth,
    sse,
    tags,
    tasks,
    users,
    web,
)
from .broker.tasks_client import TasksBusClient
from .broker.users_client import UsersBusClient
from .cache import Cache
from .chat import ChatHub
from .config import (
    AMQP_URL,
    AUTH_ENABLED,
    CACHE_ENABLED,
    CHAT_CHANNEL,
    CHAT_ENABLED,
    CHAT_HISTORY_SIZE,
    HOST,
    LOG_LEVEL,
    METRICS_ENABLED,
    OAUTH_STATE_TTL,
    PORT,
    RATE_LIMIT_CAPACITY,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_REFILL_RATE,
    REDIS_URL,
    SERVICE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    SSE_CHANNEL,
    SSE_ENABLED,
    SSE_MAX_QUEUE,
    YANDEX_OAUTH_ENABLED,
)
from .events import EventsHub
from .metrics import build_instrumentator
from .ratelimit import RateLimiter
from .sessions import OAuthStateStore, SessionStore

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# RabbitMQ client instance
rabbitmq_client: RabbitMQClient = None

# Redis cache instance
cache: Cache = None

# Redis-backed rate limiter instance
rate_limiter: RateLimiter = None

# Redis-backed session store instance
session_store: SessionStore = None

# Redis-backed one-time state tokens for the OAuth flow
oauth_state_store: OAuthStateStore = None

# Chat hub (Redis pub/sub) and its background listener task
chat_hub: ChatHub = None
chat_listener_task: asyncio.Task = None

# Task-events hub (Redis pub/sub) and its background listener task
events_hub: EventsHub = None
events_listener_task: asyncio.Task = None

# Paths that bypass rate limiting (health checks, docs, metrics, static assets)
RATE_LIMIT_EXEMPT = ("/health", "/docs", "/redoc", "/openapi.json", "/metrics")

# HTTP methods that mutate state and therefore require authentication.
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

# Write paths that must stay open (the login/logout endpoints themselves).
AUTH_EXEMPT_WRITE = ("/auth/login", "/auth/logout")


def _is_rate_limit_exempt(path: str) -> bool:
    """Return True for paths that should never be rate limited."""
    return path.startswith("/static") or path in RATE_LIMIT_EXEMPT


def _requires_auth(method: str, path: str) -> bool:
    """Return True if the request is a state-changing call that needs a session."""
    return method in WRITE_METHODS and path not in AUTH_EXEMPT_WRITE


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.

    Manages RabbitMQ connection lifecycle.
    """
    global rabbitmq_client, cache, rate_limiter, session_store, oauth_state_store
    global chat_hub, chat_listener_task
    global events_hub, events_listener_task

    # Startup
    logger.info("Starting Gateway service...")

    try:
        # Initialize RabbitMQ client
        rabbitmq_client = RabbitMQClient(amqp_url=AMQP_URL, service_name=SERVICE_NAME)

        # Connect and setup RPC client
        await rabbitmq_client.connect()
        await rabbitmq_client.setup_rpc_client()

        # Collaborators the reworked verticals ask for by dependency rather
        # than by reaching into this module.
        app.state.rabbitmq = rabbitmq_client
        app.state.tasks_bus = TasksBusClient(rabbitmq_client)
        app.state.users_bus = UsersBusClient(rabbitmq_client)

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

        # Initialize session store (fails closed: a dead Redis blocks logins
        # and authenticated writes rather than waving them through)
        session_store = SessionStore(
            redis_url=REDIS_URL,
            ttl=SESSION_TTL,
            enabled=AUTH_ENABLED,
        )
        await session_store.connect()

        # Set client in the routers that still speak to the bus raw
        comments.set_rabbitmq_client(rabbitmq_client)
        tags.set_rabbitmq_client(rabbitmq_client)
        attachments.set_rabbitmq_client(rabbitmq_client)
        auth.set_session_store(session_store)

        # Yandex OAuth needs its own one-time state tokens (CSRF protection)
        if YANDEX_OAUTH_ENABLED:
            oauth_state_store = OAuthStateStore(redis_url=REDIS_URL, ttl=OAUTH_STATE_TTL)
            await oauth_state_store.connect()
            oauth.set_session_store(session_store)
            oauth.set_state_store(oauth_state_store)

        # Chat: one pub/sub listener per gateway instance fans messages out
        # to the local WebSocket connections
        if CHAT_ENABLED:
            chat_hub = ChatHub(
                redis_url=REDIS_URL,
                channel=CHAT_CHANNEL,
                history_size=CHAT_HISTORY_SIZE,
            )
            await chat_hub.connect()
            chat_listener_task = asyncio.create_task(chat_hub.run_listener())
            chat.set_chat_hub(chat_hub)
            chat.set_session_store(session_store)

        # SSE task notifications: same pub/sub fan-out pattern as the chat,
        # publishers are the tasks write routers.
        if SSE_ENABLED:
            events_hub = EventsHub(
                redis_url=REDIS_URL,
                channel=SSE_CHANNEL,
                max_queue=SSE_MAX_QUEUE,
            )
            await events_hub.connect()
            events_listener_task = asyncio.create_task(events_hub.run_listener())
            sse.set_events_hub(events_hub)
            sse.set_session_store(session_store)
            app.state.events_hub = events_hub

        # Wire cache into the routers that use it
        app.state.cache = cache
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
        if session_store:
            await session_store.close()
        if oauth_state_store:
            await oauth_state_store.close()
        if chat_listener_task:
            chat_listener_task.cancel()
            try:
                await chat_listener_task
            except asyncio.CancelledError:
                pass
        if chat_hub:
            await chat_hub.close()
        if events_listener_task:
            events_listener_task.cancel()
            try:
                await events_listener_task
            except asyncio.CancelledError:
                pass
        if events_hub:
            await events_hub.close()
        logger.info("Gateway service stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="Task Tracker Gateway",
    description="API Gateway for Task Tracker microservices",
    version="0.1.0",
    lifespan=lifespan,
)

# Domain errors become HTTP statuses here and nowhere else. Registering the
# base class is enough: Starlette looks a handler up along type(exc).__mro__.
register_error_handlers(app)

# Filled in by the lifespan. Declared here so a dependency never meets a
# missing attribute, and so the pre-startup values are honest: no connection,
# no cache, nobody to notify.
app.state.rabbitmq = None
app.state.tasks_bus = TasksBusClient(None)
app.state.users_bus = UsersBusClient(None)
app.state.cache = None
app.state.events_hub = None


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


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require a valid session for state-changing requests.

    Reads are public; POST/PUT/PATCH/DELETE need a session cookie (except the
    login/logout endpoints). Fails closed: with the session store down, writes
    are rejected rather than allowed.
    """
    if AUTH_ENABLED and session_store is not None and _requires_auth(request.method, request.url.path):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        user = await session_store.get(token) if token else None
        if user is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

    return await call_next(request)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(web.router)
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(comments.router)
app.include_router(tags.router)
app.include_router(attachments.router)
app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(chat.router)
app.include_router(sse.router)

# Expose Prometheus metrics at /metrics. Instrumentation is wired last so its
# middleware sits outermost and times every request -- including the 429s
# produced by the rate-limit middleware above.
if METRICS_ENABLED:
    build_instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME, "rabbitmq_connected": rabbitmq_client is not None}


# Application entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tracker_gateway.main:app", host=HOST, port=PORT, reload=True, log_level=LOG_LEVEL.lower())
