"""
Universal RabbitMQ client for microservices and gateway.

Supports:
- RPC (Request-Reply) pattern for synchronous calls
- Consumer pattern for message processing
- Event publishing for async communication
"""

import asyncio
import json
import uuid
from typing import Optional, Callable, Dict, Any, Awaitable
import logging

import aio_pika
from aio_pika import Message, IncomingMessage, ExchangeType
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractQueue, AbstractExchange

logger = logging.getLogger(__name__)


class RabbitMQClient:
    """
    Universal RabbitMQ client for both Gateway and Microservices.
    
    Features:
    - RPC calls with timeout (for Gateway)
    - Message consumption (for Microservices)
    - Event publishing (for all services)
    """
    
    def __init__(self, amqp_url: str, service_name: Optional[str] = None):
        """
        Initialize RabbitMQ client.
        
        Args:
            amqp_url: RabbitMQ connection URL (e.g., 'amqp://guest:guest@localhost/')
            service_name: Optional service name for logging and queue naming
        """
        self.amqp_url = amqp_url
        self.service_name = service_name or "unnamed"
        
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        
        # For RPC pattern
        self.callback_queue: Optional[AbstractQueue] = None
        self.futures: Dict[str, asyncio.Future] = {}
        
        # For event publishing
        self.events_exchange: Optional[AbstractExchange] = None
        
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
            auto_delete=True
        )
        
        # Start consuming responses
        await self.callback_queue.consume(self._on_rpc_response)
        
        logger.info(f"[{self.service_name}] RPC client ready")
    
    async def call(
        self,
        queue_name: str,
        message: Dict[str, Any],
        timeout: float = 30.0
    ) -> Dict[str, Any]:
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
                ),
                routing_key=queue_name,
            )
            
            logger.debug(
                f"[{self.service_name}] RPC call to {queue_name}, "
                f"correlation_id={correlation_id}"
            )
            
            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            logger.error(
                f"[{self.service_name}] RPC timeout for {queue_name}, "
                f"correlation_id={correlation_id}"
            )
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
                logger.warning(
                    f"[{self.service_name}] No pending future for "
                    f"correlation_id={correlation_id}"
                )
                return
            
            try:
                response = json.loads(message.body.decode())
                future.set_result(response)
                logger.debug(
                    f"[{self.service_name}] RPC response received, "
                    f"correlation_id={correlation_id}"
                )
            except Exception as e:
                logger.error(f"[{self.service_name}] Error processing RPC response: {e}")
                future.set_exception(e)
    
    # ==================== Consumer Pattern (for Microservices) ====================
    
    async def consume(
        self,
        queue_name: str,
        callback: Callable[[Dict[str, Any], IncomingMessage], Awaitable[Dict[str, Any]]],
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
        queue = await self.channel.declare_queue(
            name=queue_name,
            durable=True,
            auto_delete=False
        )
        
        # Set QoS
        await self.channel.set_qos(prefetch_count=prefetch_count)
        
        # Create wrapper to handle reply
        async def wrapped_callback(message: IncomingMessage) -> None:
            async with message.process():
                try:
                    # Parse incoming message
                    payload = json.loads(message.body.decode())
                    
                    logger.debug(
                        f"[{self.service_name}] Received message from {queue_name}, "
                        f"correlation_id={message.correlation_id}"
                    )
                    
                    # Process message
                    response = await callback(payload, message)
                    
                    # Send response if reply_to is set (RPC pattern)
                    if message.reply_to:
                        await self.channel.default_exchange.publish(
                            Message(
                                body=json.dumps(response).encode(),
                                correlation_id=message.correlation_id,
                                content_type="application/json",
                            ),
                            routing_key=message.reply_to,
                        )
                        logger.debug(
                            f"[{self.service_name}] Sent response to {message.reply_to}, "
                            f"correlation_id={message.correlation_id}"
                        )
                    
                except Exception as e:
                    logger.error(
                        f"[{self.service_name}] Error processing message: {e}",
                        exc_info=True
                    )
                    
                    # Send error response if reply_to is set
                    if message.reply_to:
                        error_response = {
                            "success": False,
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                        await self.channel.default_exchange.publish(
                            Message(
                                body=json.dumps(error_response).encode(),
                                correlation_id=message.correlation_id,
                                content_type="application/json",
                            ),
                            routing_key=message.reply_to,
                        )
        
        # Start consuming
        await queue.consume(wrapped_callback)
        
        logger.info(
            f"[{self.service_name}] Started consuming from {queue_name}, "
            f"prefetch={prefetch_count}"
        )
    
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
        
        logger.info(
            f"[{self.service_name}] Event publisher ready, "
            f"exchange={exchange_name}"
        )
    
    async def publish_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        routing_key: Optional[str] = None
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
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self.events_exchange.publish(
            Message(
                body=json.dumps(message).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )
        
        logger.debug(
            f"[{self.service_name}] Published event: {event_type}, "
            f"routing_key={routing_key}"
        )
    
    async def subscribe_to_events(
        self,
        queue_name: str,
        binding_keys: list[str],
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        exchange_name: str = "events"
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
                    logger.debug(
                        f"[{self.service_name}] Received event: "
                        f"{event.get('event_type')}"
                    )
                    await callback(event)
                except Exception as e:
                    logger.error(
                        f"[{self.service_name}] Error processing event: {e}",
                        exc_info=True
                    )
        
        # Start consuming
        await queue.consume(wrapped_callback)
        
        logger.info(
            f"[{self.service_name}] Subscribed to events: {binding_keys}, "
            f"queue={queue_name}"
        )


