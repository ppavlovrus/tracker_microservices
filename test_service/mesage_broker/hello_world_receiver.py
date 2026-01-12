import aio_pika
import asyncio

from aio_pika.abc import AbstractIncomingMessage


async def on_message(message: AbstractIncomingMessage) -> None:
    """
    on_message doesn't necessarily have to be defined as async.
    Here it is to show that it's possible.
    """
    print(" [x] Received message %r" % message)
    print("Message body is: %r" % message.body)

    print("Before sleep!")
    await asyncio.sleep(5)  # Represents async I/O operations
    print("After sleep!")

async def receiver() -> None:
    connection = await aio_pika.connect("amqp://guest:guest@localhost:5672/")
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("hello")
        await queue.consume(on_message, no_ack=True)
        print(" [*] Waiting for messages. To exit press CTRL+C")
        await asyncio.Future()

asyncio.run(receiver())