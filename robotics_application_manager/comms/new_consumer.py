"""
WebSocket consumer module for the Robotics Application Manager (RAM).

Handles client connections, message processing, and communication with manager queue.
"""

import json
import logging
from queue import Queue
from uuid import uuid4
from datetime import datetime

from manager.comms.consumer_message import (
    ManagerConsumerMessageException,
    ManagerConsumerMessage,
)
from manager.comms.websocket_server import WebsocketServer
from manager.ram_logging.log_manager import LogManager


class ManagerConsumer:
    """
    Websocket server consumer for new Robotics Application Manager aka: RAM.

    Supports single client connection to RAM
    TODO: Better handling of single client connections, closing and redirecting
    """

    def __init__(self, host, port, manager_queue: Queue):
        """
        Initialize the ManagerConsumer with host, port, and manager_queue.

        Args:
            host (str): The host address for the WebSocket server.
            port (int): The port number for the WebSocket server.
            manager_queue (Queue): The queue for communication with the manager.
        """
        self.host = host
        self.port = port
        self.server = WebsocketServer(host=host, port=port, loglevel=logging.INFO)

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

        self.server.set_fn_new_client(self.handle_client_new)
        self.server.set_fn_client_left(self.handle_client_disconnect)
        self.server.set_fn_message_received(self.handle_message_received)
        self.client = None
        self.manager_queue = manager_queue

    def handle_client_new(self, client, server):
        """
        Handle a new client connection event.

        Args:
            client: The client object representing the connected client.
            server: The WebSocket server instance.
        """
        LogManager.logger.info(f"client connected: {client}")
        self.client = client
        self.server.deny_new_connections()

    def handle_client_disconnect(self, client, server):
        """
        Handle a client disconnection event.

        Args:
            client: The client object representing the disconnected client.
            server: The WebSocket server instance.
        """
        if client is None:
            return
        LogManager.logger.info(f"client disconnected: {client}")
        now = datetime.now()
        time_string = now.strftime("%H:%M:%S")
        print(time_string)
        message = ManagerConsumerMessage(
            **{"id": str(uuid4()), "command": "disconnect"}
        )
        self.manager_queue.put(message)
        self.client = None
        self.server.allow_new_connections()

    def handle_message_received(self, client, server, websocket_message):
        """
        Handle a message received from a client.

        Args:
            client: The client object that sent the message.
            server: The WebSocket server instance.
            websocket_message (str): The message received from the client.
        """
        LogManager.logger.info(
            f"message received length: {len(websocket_message)} from client {client}"
        )
        LogManager.logger.info(
            f"message received: {websocket_message} from client {client}"
        )
        message = None
        try:
            s = json.loads(websocket_message)
            message = ManagerConsumerMessage(**s)
            self.manager_queue.put(message)
        except Exception as e:
            if message is not None:
                ex = ManagerConsumerMessageException(id=message.id, message=str(e))
            else:
                ex = ManagerConsumerMessageException(id=str(uuid4()), message=str(e))
            self.server.send_message(client, str(ex))
            raise e

    def send_message(self, message_data, command=None):
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

            self.server.send_message(self.client, str(message))

    def start(self):
        """Start the WebSocket server in a separate thread."""
        self.server.run_forever(threaded=True)

    def stop(self):
        """Stop the WebSocket server gracefully."""
        self.server.shutdown_gracefully()
