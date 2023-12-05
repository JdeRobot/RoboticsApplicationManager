import threading
import json

from websocket_server import WebsocketServer

from src.manager.ram_logging.log_manager import LogManager


class Server(threading.Thread):
    def __init__(self, port, callback,):
        super().__init__()
        self.update_callback = callback
        self.server = WebsocketServer(port, host='127.0.0.1')
        self.server.set_fn_new_client(self.on_open)
        self.server.set_fn_client_left(self.on_close)
        self.server.set_fn_message_received(self.on_message)
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            self.server.run_forever()
            if self._stop.isSet():
                return
        except Exception as ex:
            LogManager.logger.exception(ex)

    def stop(self) -> None:
        self._stop.set()
        self.server.shutdown()

    def send(self, client, data):
        self.server.send_message(client, data)

    def on_message(self, client, server, message):
        payload = json.loads(message[4:])
        self.update_callback(payload)
        client.send("#ack")
        LogManager.logger.debug(
            f"Message received from exercise template: {message[:30]}")

    def on_close(self, client, server):
        LogManager.logger.info("Connection with client closed")

    def on_open(self, client, server):
        LogManager.logger.info("New client connected")
