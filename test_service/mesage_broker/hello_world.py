import aio_pika
import asyncio

async def main() -> None:
    #Perform connection
    connection = await aio_pika.connect("amqp://guest:guest@localhost:5672/")
    #Work with connection as context - automatic close when leave context
    async with connection:
        #Get channel
        channel = await connection.channel()
        #Declare queue
        queue = await channel.declare_queue("hello")
        #Sending message
        print("Sending message")
        await channel.default_exchange.publish(aio_pika.Message(body=b"Hello, World!"),
                                               routing_key=queue.name)
        print("Send")
        await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())