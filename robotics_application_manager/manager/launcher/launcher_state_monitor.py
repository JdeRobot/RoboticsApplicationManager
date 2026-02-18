from manager.libs.server import Server
from manager.ram_logging.log_manager import LogManager
from manager.comms.new_consumer import ManagerConsumer
from typing import Optional
from manager.libs.file_watchdog import FileWatchdog


class LauncherStateMonitor:
    file: str
    consumer: ManagerConsumer
    running: bool = False
    acceptsMsgs: bool = True

    def __init__(self, type, module, file, consumer):
        self.file = file
        self.consumer = consumer
        self.server = FileWatchdog("/tmp/tree_state", self.update)

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
