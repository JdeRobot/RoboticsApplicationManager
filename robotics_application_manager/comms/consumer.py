"""
WebSocket consumer module for the Robotics Application Manager (RAM).

Handles client connections, message processing, and communication with manager queue.
"""

import json
import logging
from queue import Queue
from uuid import uuid4
from datetime import datetime

from .consumer_message import (
    ManagerConsumerMessageException,
    ManagerConsumerMessage,
)
from .websocket_server import WebsocketServer
from robotics_application_manager import LogManager
from websockets.asyncio.server import serve
import asyncio

class ManagerConsumer:
    """
    Websocket server consumer for new Robotics Application Manager aka: RAM.

    Supports single client connection to RAM
    TODO: Better handling of single client connections, closing and redirecting
    """

    def __init__(self, host, port, process_callback):
        """
        Initialize the ManagerConsumer with host, port, and manager_queue.

        Args:
            host (str): The host address for the WebSocket server.
            port (int): The port number for the WebSocket server.
            manager_queue (Queue): The queue for communication with the manager.
        """
        self.host = host
        self.port = port
        self.client = None
        self.process_callback = process_callback
        self.server_task = None

        # Configurar el logger de websocket_server para salida a consola
        ws_logger = logging.getLogger("websocket_server.websocket_server")
        ws_logger.propagate = False
        ws_logger.setLevel(logging.INFO)
        ws_logger.handlers.clear()
        ws_formatter = logging.Formatter(
            "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s] "
            "(%(name)s)  %(message)s",
            "%H:%M:%S",
        )
        ws_console_handler = logging.StreamHandler()
        ws_console_handler.setFormatter(ws_formatter)
        ws_logger.addHandler(ws_console_handler)

    # Use the __await__ method to make the class awaitable
    def __await__(self):
        # Call ls the constructor and returns the instance
        return self.create().__await__()

    # A method that creates an instance of the class asynchronously
    async def create(self):
        self.server = await serve(self.manage_conection, self.host, self.port)
        return self

    async def manage_conection(self, websocket):
        if self.client is not None:
          await websocket.close()
          return

        try:
            self.client = websocket # Register client
            LogManager.logger.info(f"client connected: {self.client}")

            await self.process_msg(websocket)
        finally:
            now = datetime.now()
            time_str = now.strftime("%H:%M:%S")
            LogManager.logger.info(f"Client disconnected {time_str}: {self.client}")
            message = ManagerConsumerMessage(id=str(uuid4()), command="disconnect")
            await self.send_message(message)
            self.client = None

    async def process_msg(self, websocket):
        while True:
            async for raw_msg in websocket:
              try:
                  json_msg = json.loads(raw_msg)
                  await self.process_callback(ManagerConsumerMessage(**json_msg))
              except Exception as e:
                  ex = ManagerConsumerMessageException(id=str(uuid4()), message=str(e))
                  await self.send_message(ex)
                  LogManager.logger.error(e, exc_info=True)

    async def send_message(self, message_data, command=None):
            """
            Send a message to the connected client.

            Args:
                message_data: The message data to send, can be a ManagerConsumerMessage,
                    ManagerConsumerMessageException, or other data.
                command (str, optional): The command associated with the message,
                    used if message_data is not a ManagerConsumerMessage.
            """
            if self.client is not None and self.server is not None:
                if isinstance(message_data, ManagerConsumerMessage):
                    message = message_data
                elif isinstance(message_data, ManagerConsumerMessageException):
                    message = message_data.consumer_message()
                else:
                    message = ManagerConsumerMessage(
                        id=str(uuid4()), command=command, data=message_data
                    )

                await self.client.send(str(message))

    def start(self):
        """Start the WebSocket server in a separate thread."""
        self.server_task = asyncio.create_task(self.server.serve_forever())

    async def stop(self):
        """Stop the WebSocket server gracefully."""
        await self.server.close()
        if self.server_task is not None:
          self.server_task.cancel()
          await self.server_task
