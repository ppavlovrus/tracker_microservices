"""Gateway startup and shutdown.

Every collaborator owns its own ``init_*``/``close_*`` pair, next to the class
it builds. What is left here is the order they are opened in and the order
they are closed in -- a list, not a decision tree. A feature switch belongs to
the module that knows what being switched off means for it, which is why there
is no ``if`` in the sequence below.

``app.state`` carries only what ``api/deps.py`` resolves per request. Anything
else stays with its owning module: a second copy on the app would go stale the
moment ``close_*`` runs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routers import attachments, auth, chat, comments, oauth, sse, tags
from .broker import bus
from .broker import chat as chat_broker
from .broker import events as events_broker
from .broker.tasks_client import TasksBusClient
from .broker.users_client import UsersBusClient
from .middleware.ratelimit import close_rate_limiter, init_rate_limiter
from .storage import cache as cache_storage
from .storage import sessions

logger = logging.getLogger(__name__)


async def startup(app: FastAPI) -> None:
    """Open every collaborator, then hand them to the routers."""
    rabbitmq = await bus.init_bus()
    app.state.rabbitmq = rabbitmq
    app.state.tasks_bus = TasksBusClient(rabbitmq)
    app.state.users_bus = UsersBusClient(rabbitmq)

    app.state.cache = await cache_storage.init_cache()
    await init_rate_limiter()
    await sessions.init_sessions()
    await sessions.init_oauth_state()
    await chat_broker.init_chat()
    app.state.events_hub = await events_broker.init_events()

    wire_routers()


async def shutdown() -> None:
    """Close the collaborators in the order the previous lifespan used."""
    await bus.close_bus()
    await cache_storage.close_cache()
    await close_rate_limiter()
    await sessions.close_sessions()
    await sessions.close_oauth_state()
    await chat_broker.close_chat()
    await events_broker.close_events()


def wire_routers() -> None:
    """Hand the collaborators to the routers that still read module globals.

    The conditions are deliberate, not leftovers. Chat and SSE check the
    session before they check their hub, so a gateway with the feature off
    answers 401 today; wiring the session store unconditionally would silently
    turn that into 503. The setters disappear when these routers move to
    ``Depends`` like tasks and users did -- until then the debt sits here, in
    one function, rather than spread through the startup sequence.
    """
    comments.set_rabbitmq_client(bus.client)
    tags.set_rabbitmq_client(bus.client)
    tags.set_cache(cache_storage.cache)
    attachments.set_rabbitmq_client(bus.client)
    auth.set_session_store(sessions.session_store)

    if sessions.oauth_state_store is not None:
        oauth.set_session_store(sessions.session_store)
        oauth.set_state_store(sessions.oauth_state_store)

    if chat_broker.hub is not None:
        chat.set_chat_hub(chat_broker.hub)
        chat.set_session_store(sessions.session_store)

    if events_broker.hub is not None:
        sse.set_events_hub(events_broker.hub)
        sse.set_session_store(sessions.session_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring the gateway up, serve, then take it down again."""
    logger.info("Starting Gateway service...")
    try:
        await startup(app)
    except Exception as e:
        logger.error(f"Failed to start Gateway: {e}", exc_info=True)
        raise
    logger.info("Gateway service started successfully")

    yield

    logger.info("Shutting down Gateway service...")
    try:
        await shutdown()
        logger.info("Gateway service stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
