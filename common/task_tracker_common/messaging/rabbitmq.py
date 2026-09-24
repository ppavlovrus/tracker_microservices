"""
Universal RabbitMQ client for microservices and gateway.

Supports:
- RPC (Request-Reply) pattern for synchronous calls
- Consumer pattern for message processing
- Event publishing for async communication
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika import ExchangeType, IncomingMessage, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractExchange,
    AbstractQueue,
)

logger = logging.getLogger(__name__)


def _command_header(message: dict[str, Any]) -> dict[str, str] | None:
    """The command name, for the message header. None when there is no command."""
    command = message.get("command")
    return {"command": command} if isinstance(command, str) else None


class RabbitMQClient:
    """
    Universal RabbitMQ client for both Gateway and Microservices.

    Features:
    - RPC calls with timeout (for Gateway)
    - Message consumption (for Microservices)
    - Event publishing (for all services)
    """

    def __init__(self, amqp_url: str, service_name: str | None = None):
        """
        Initialize RabbitMQ client.
        Args:
            amqp_url: RabbitMQ connection URL (e.g., 'amqp://guest:guest@localhost/')
            service_name: Optional service name for logging and queue naming
        """
        self.amqp_url = amqp_url
        self.service_name = service_name or "unnamed"

        self.connection: AbstractConnection | None = None
        self.channel: AbstractChannel | None = None

        # For RPC pattern
        self.callback_queue: AbstractQueue | None = None
        self.futures: dict[str, asyncio.Future] = {}

        # For event publishing
        self.events_exchange: AbstractExchange | None = None

        # Consumers registered by consume(), so shutdown can cancel them, and
        # the handler tasks currently in flight. aiormq delivers every message
        # in a task of its own, which is what makes handlers concurrent -- and
        # also what makes closing the connection during shutdown able to kill
        # one halfway through its transaction.
        self._consumers: list[tuple[AbstractQueue, str]] = []
        self._inflight: set[asyncio.Task] = set()

    async def connect(self) -> None:
        """Establish connection to RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(self.amqp_url)
            self.channel = await self.connection.channel()

            # Set QoS for better message distribution
            await self.channel.set_qos(prefetch_count=10)

            logger.info(f"[{self.service_name}] Connected to RabbitMQ")

        except Exception as e:
            logger.error(f"[{self.service_name}] Failed to connect to RabbitMQ: {e}")
            raise

    async def close(self) -> None:
        """Close RabbitMQ connection."""
        try:
            if self.channel and not self.channel.is_closed:
                await self.channel.close()

            if self.connection and not self.connection.is_closed:
                await self.connection.close()

            logger.info(f"[{self.service_name}] Disconnected from RabbitMQ")

        except Exception as e:
            logger.error(f"[{self.service_name}] Error closing connection: {e}")

    # ==================== RPC Pattern (for Gateway) ====================

    async def setup_rpc_client(self) -> None:
        """
        Setup RPC client (for Gateway).
        Creates callback queue for receiving responses.
        """
        if not self.channel:
            raise RuntimeError("Channel not initialized. Call connect() first.")

        # Create exclusive callback queue for responses
        self.callback_queue = await self.channel.declare_queue(
            name="",  # Let RabbitMQ generate unique name
            exclusive=True,
            auto_delete=True,
        )

        # Start consuming responses
        await self.callback_queue.consume(self._on_rpc_response)

        logger.info(f"[{self.service_name}] RPC client ready")

    async def call(self, queue_name: str, message: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        """
        Make RPC call to a microservice.

        Args:
            queue_name: Target queue name (e.g., 'tasks.commands')
            message: Message payload
            timeout: Response timeout in seconds

        Returns:
            Response from microservice

        Raises:
            asyncio.TimeoutError: If response not received within timeout
            RuntimeError: If RPC client not setup
        """
        if not self.callback_queue:
            raise RuntimeError("RPC client not setup. Call setup_rpc_client() first.")

        correlation_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self.futures[correlation_id] = future

        try:
            # Publish request
            await self.channel.default_exchange.publish(
                Message(
                    body=json.dumps(message).encode(),
                    correlation_id=correlation_id,
                    reply_to=self.callback_queue.name,
                    content_type="application/json",
                    # The command travels in a header as well as in the body.
                    # Nothing routes on it yet -- the payload stays the single
                    # source of truth -- but it makes the command readable in
                    # the management UI and in a firehose trace without
                    # decoding the body, and it is what a headers exchange
                    # would bind on if this ever moves to broker-side routing.
                    headers=_command_header(message),
                ),
                routing_key=queue_name,
            )

            logger.debug(f"[{self.service_name}] RPC call to {queue_name}, correlation_id={correlation_id}")

            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except TimeoutError:
            logger.error(f"[{self.service_name}] RPC timeout for {queue_name}, correlation_id={correlation_id}")
            raise
        finally:
            # Cleanup
            self.futures.pop(correlation_id, None)

    async def _on_rpc_response(self, message: IncomingMessage) -> None:
        """Handle RPC response (internal callback)."""
        async with message.process():
            correlation_id = message.correlation_id

            if not correlation_id:
                logger.warning(f"[{self.service_name}] Received message without correlation_id")
                return

            future = self.futures.get(correlation_id)
            if not future or future.done():
                logger.warning(f"[{self.service_name}] No pending future for correlation_id={correlation_id}")
                return

            try:
                response = json.loads(message.body.decode())
                future.set_result(response)
                logger.debug(f"[{self.service_name}] RPC response received, correlation_id={correlation_id}")
            except Exception as e:
                logger.error(f"[{self.service_name}] Error processing RPC response: {e}")
                future.set_exception(e)

    # ==================== Consumer Pattern (for Microservices) ====================

    async def consume(
        self,
        queue_name: str,
        callback: Callable[[dict[str, Any], IncomingMessage], Awaitable[dict[str, Any]]],
        prefetch_count: int = 10,
    ) -> None:
        """
        Start consuming messages from a queue (for Microservices).

        Args:
            queue_name: Queue to consume from
            callback: Async function to process message and return response
            prefetch_count: Number of messages to prefetch
        """
        if not self.channel:
            raise RuntimeError("Channel not initialized. Call connect() first.")

        # Declare queue
        queue = await self.channel.declare_queue(name=queue_name, durable=True, auto_delete=False)

        # Set QoS
        await self.channel.set_qos(prefetch_count=prefetch_count)

        # Create wrapper to handle reply
        async def wrapped_callback(message: IncomingMessage) -> None:
            task = asyncio.current_task()
            if task is not None:
                self._inflight.add(task)
            try:
                await self._handle_delivery(message, callback, queue_name)
            finally:
                self._inflight.discard(task)

        # Start consuming. The tag is what lets shutdown stop new deliveries
        # without tearing down the connection the in-flight handlers still use.
        consumer_tag = await queue.consume(wrapped_callback)
        self._consumers.append((queue, consumer_tag))

        logger.info(f"[{self.service_name}] Started consuming from {queue_name}, prefetch={prefetch_count}")

    async def _reply(self, message: IncomingMessage, body: dict[str, Any]) -> None:
        """Answer an RPC request. A message with no reply_to wants no answer."""
        if not message.reply_to:
            return
        await self.channel.default_exchange.publish(
            Message(
                body=json.dumps(body).encode(),
                correlation_id=message.correlation_id,
                content_type="application/json",
            ),
            routing_key=message.reply_to,
        )
        logger.debug(
            f"[{self.service_name}] Sent response to {message.reply_to}, "
            f"correlation_id={message.correlation_id}"
        )

    async def _handle_delivery(
        self,
        message: IncomingMessage,
        callback: Callable[[dict[str, Any], IncomingMessage], Awaitable[dict[str, Any]]],
        queue_name: str,
    ) -> None:
        """Run one delivery: parse, hand to the callback, answer, acknowledge."""
        async with message.process():
            try:
                payload = json.loads(message.body.decode())
                logger.debug(
                    f"[{self.service_name}] Received message from {queue_name}, "
                    f"correlation_id={message.correlation_id}"
                )
                await self._reply(message, await callback(payload, message))
            except Exception as e:
                logger.error(f"[{self.service_name}] Error processing message: {e}", exc_info=True)
                await self._reply(
                    message,
                    {"success": False, "error": "Internal error", "error_type": type(e).__name__},
                )

    async def stop_consuming(self, drain_timeout: float = 30.0) -> None:
        """Stop taking new messages, then let the ones in flight finish.

        Without this, shutdown closed the connection while handlers were still
        running: aiormq gives each delivery its own task, so a handler could be
        halfway through a transaction when the channel went away. Cancelling
        the consumer first means the broker stops delivering and redelivers
        whatever was never acknowledged.
        """
        for queue, tag in self._consumers:
            try:
                await queue.cancel(tag)
            except Exception as e:
                logger.warning(f"[{self.service_name}] Could not cancel consumer {tag}: {e}")
        self._consumers.clear()

        if not self._inflight:
            return

        logger.info(f"[{self.service_name}] Waiting for {len(self._inflight)} message(s) in flight")
        _, pending = await asyncio.wait(set(self._inflight), timeout=drain_timeout)

        if pending:
            # Left running on purpose: the broker redelivers what was never
            # acknowledged, and killing a handler mid-transaction is worse.
            logger.error(f"[{self.service_name}] {len(pending)} handler(s) still running after {drain_timeout}s")

    # ==================== Event Publishing (for all services) ====================

    async def setup_event_publisher(self, exchange_name: str = "events") -> None:
        """
        Setup event publisher for publishing domain events.

        Args:
            exchange_name: Name of the events exchange
        """
        if not self.channel:
            raise RuntimeError("Channel not initialized. Call connect() first.")

        # Declare topic exchange for events
        self.events_exchange = await self.channel.declare_exchange(
            name=exchange_name,
            type=ExchangeType.TOPIC,
            durable=True,
        )

        logger.info(f"[{self.service_name}] Event publisher ready, exchange={exchange_name}")

    async def publish_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        routing_key: str | None = None,
    ) -> None:
        """
        Publish domain event.

        Args:
            event_type: Type of event (e.g., 'task.created', 'user.updated')
            event_data: Event payload
            routing_key: Optional routing key (defaults to event_type)
        """
        if not self.events_exchange:
            raise RuntimeError("Event publisher not setup. Call setup_event_publisher() first.")

        routing_key = routing_key or event_type

        message = {
            "event_type": event_type,
            "data": event_data,
            "timestamp": asyncio.get_event_loop().time(),
        }

        await self.events_exchange.publish(
            Message(
                body=json.dumps(message).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

        logger.debug(f"[{self.service_name}] Published event: {event_type}, routing_key={routing_key}")

    async def subscribe_to_events(
        self,
        queue_name: str,
        binding_keys: list[str],
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        exchange_name: str = "events",
    ) -> None:
        """
        Subscribe to domain events.

        Args:
            queue_name: Queue name for this subscriber
            binding_keys: List of routing keys to bind (e.g., ['task.*', 'user.created'])
            callback: Async function to process event
            exchange_name: Name of the events exchange
        """
        if not self.channel:
            raise RuntimeError("Channel not initialized. Call connect() first.")

        # Declare exchange
        exchange = await self.channel.declare_exchange(
            name=exchange_name,
            type=ExchangeType.TOPIC,
            durable=True,
        )

        # Declare queue
        queue = await self.channel.declare_queue(
            name=queue_name,
            durable=True,
        )

        # Bind queue to exchange with routing keys
        for binding_key in binding_keys:
            await queue.bind(exchange, routing_key=binding_key)

        # Create wrapper
        async def wrapped_callback(message: IncomingMessage) -> None:
            async with message.process():
                try:
                    event = json.loads(message.body.decode())
                    logger.debug(f"[{self.service_name}] Received event: {event.get('event_type')}")
                    await callback(event)
                except Exception as e:
                    logger.error(
                        f"[{self.service_name}] Error processing event: {e}",
                        exc_info=True,
                    )

        # Start consuming
        await queue.consume(wrapped_callback)

        logger.info(f"[{self.service_name}] Subscribed to events: {binding_keys}, queue={queue_name}")
