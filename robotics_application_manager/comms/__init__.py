"""
Communication module for Robotics Application Manager.

Provides classes and utilities for handling communication
between the manager backend and client applications.
"""

from .new_consumer import ManagerConsumer
from .consumer_message import ManagerConsumerMessageException, ManagerConsumerMessage
from .thread import ThreadWithLoggedException, WebsocketServerThread
from .websocket_server import WebsocketServer
