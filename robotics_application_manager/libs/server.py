import threading
import json

from websockets.asyncio.server import serve
import asyncio

from robotics_application_manager import LogManager


class Server:
    def __init__(
        self,
        port,
        callback,
    ):
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
        self.server = await serve(self.manage_conection, "127.0.0.1", self.port)
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
        finally:
            LogManager.logger.info("Connection with client closed")
            await self.send_message(message)
            with self.client_lock:
              self.client = None

    async def process_msg(self, websocket):
        while True:
            async for raw_msg in websocket:
              try:
                  json_msg = json.loads(raw_msg)
                  LogManager.logger.debug(f"Message received from template: {raw_msg[:30]}")
                  await self.update_callback(json_msg)
              except Exception as e:
                  ex = ManagerConsumerMessageException(id=str(uuid4()), message=str(e))
                  await self.send_message(ex)
                  LogManager.logger.error(e, exc_info=True)

    async def send(self, data):
        with self.client_lock:
            if self.client is not None:
                await self.client.send(data)

    def start(self):
        """Start the WebSocket server in a separate thread."""
        self.server_task = asyncio.create_task(self.server.serve_forever())

    async def stop(self):
        """Stop the WebSocket server gracefully."""
        await self.server.close()
        if self.server_task is not None:
          self.server_task.cancel()
          await self.server_task
