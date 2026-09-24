"""The gateway's RabbitMQ connection and its lifecycle.

One client per process, opened at startup and closed at shutdown. The RPC
clients in this package (``tasks_client``, ``users_client``) are built on top
of it; the routers reach it through ``app.state.rabbitmq``.
"""

import logging

from task_tracker_common.messaging import RabbitMQClient

from ..core.config import AMQP_URL, SERVICE_NAME

logger = logging.getLogger(__name__)

client: RabbitMQClient | None = None


async def init_bus() -> RabbitMQClient:
    """Connect to RabbitMQ and set up the RPC client.

    Unlike the Redis-backed collaborators, this one is not best-effort: a
    gateway that cannot reach the bus has nothing to serve, so a failure here
    propagates and stops startup.
    """
    global client
    client = RabbitMQClient(amqp_url=AMQP_URL, service_name=SERVICE_NAME)
    await client.connect()
    await client.setup_rpc_client()
    logger.info(f"RabbitMQ: {AMQP_URL}")
    return client


async def close_bus() -> None:
    global client
    if client is not None:
        await client.close()
        client = None
