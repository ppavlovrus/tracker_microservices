"""Gateway FastAPI application.

Assembly only: what the app is made of and in which order the pieces are
stacked. How each piece starts and stops lives in ``lifespan.py`` and in the
module that owns it.
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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
from .core.config import HOST, LOG_LEVEL, METRICS_ENABLED, PORT, SERVICE_NAME
from .core.metrics import build_instrumentator
from .lifespan import lifespan
from .middleware.auth import AuthMiddleware
from .middleware.ratelimit import RateLimitMiddleware

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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

# Middleware. Starlette runs the last one added first, so the limiter sits
# inside the auth check -- the order the decorator-based version produced.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)

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
    return {"status": "healthy", "service": SERVICE_NAME, "rabbitmq_connected": app.state.rabbitmq is not None}


# Application entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tracker_gateway.main:app", host=HOST, port=PORT, reload=True, log_level=LOG_LEVEL.lower())
