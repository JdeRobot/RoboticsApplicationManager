import threading
import json

from websockets.asyncio.server import serve
import asyncio
from uuid import uuid4

from robotics_application_manager import LogManager
from robotics_application_manager.comms import (
    ManagerConsumerMessageException,
)

class Server:
    def __init__(
        self,
        port,
        callback,
    ):
        self.host = "127.0.0.1"
        self.port = port
        self.update_callback = callback
        self.client = None
        self.client_lock = threading.Lock()  # Used to avoid concurrency problems
        self._stop = threading.Event()
        LogManager.logger.info("Server Launched")

    # Use the __await__ method to make the class awaitable
    def __await__(self):
        # Call ls the constructor and returns the instance
        return self.create().__await__()

    # A method that creates an instance of the class asynchronously
    async def create(self):
        self.server = await serve(self.manage_conection, self.host, self.port, start_serving=False,ping_interval=None, ping_timeout=None)
        return self

    async def manage_conection(self, websocket):
        with self.client_lock:
          if self.client is not None:
            await websocket.close()
            return

        try:
            with self.client_lock:
              self.client = websocket # Register client
            LogManager.logger.info(f"Client connected: {self.client}")

            await self.process_msg(websocket)
        except Exception as e:
          LogManager.logger.info(f"Client disconnected: {str(e)}")
          pass
        finally:
            LogManager.logger.info("Connection with client closed")
            with self.client_lock:
              self.client = None

    async def process_msg(self, websocket):
      async for raw_msg in websocket:
        try:
            json_msg = json.loads(raw_msg)
            await self.update_callback(json_msg)
        except Exception as e:
            ex = ManagerConsumerMessageException(id=str(uuid4()), message=str(e))
            await self.send(ex.consumer_message())
            LogManager.logger.error(e, exc_info=True)

    async def send(self, data):
        with self.client_lock:
            if self.client is not None:
                await self.client.send(data)

    async def start(self):
        """Start the WebSocket server in a separate thread."""
        await self.server.start_serving()

    async def stop(self):
        """Stop the WebSocket server gracefully."""
        self.server.close()
        await self.server.wait_closed()
