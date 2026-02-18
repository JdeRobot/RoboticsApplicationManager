from robotics_application_manager.libs import Server
from robotics_application_manager import LogManager
from robotics_application_manager.comms import ManagerConsumer
from typing import Optional


class LauncherWebGui:
    internal_port: int
    consumer: ManagerConsumer
    running: bool = False
    acceptsMsgs: bool = True

    def __init__(self, type, module, internal_port, consumer):
        self.internal_port = internal_port
        self.consumer = consumer
        self.server = Server(self.internal_port, self.update)

    def update(self, data):
        LogManager.logger.debug(f"Sending update to client")
        if self.consumer is not None:
            self.consumer.send_message({"update": data}, command="update")

    def run(self, config_file, callback):
        self.server.start()
        self.running = True

    def get_msg(self, data):
        self.server.send(data)

    def is_running(self):
        return self.running

    def terminate(self):
        self.server.stop()
        self.running = False

    def pause(self):
        pass

    def unpause(self):
        pass

    def reset(self):
        pass

    def died(self):
        pass

    def from_config(cls, config):
        obj = cls(**config)
        return obj
