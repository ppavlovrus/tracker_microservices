import asyncio
import aio_pika

class PbMqClient:
    connection = None
    queue_name = None
    channel = None
    queue = None

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def send_message(self, message: str):
        pass

    async def receive_message(self):
        pass

    async def close(self):
        pass
    def __init__(self, queue_name: str):
        self.queue_name = queue_name

