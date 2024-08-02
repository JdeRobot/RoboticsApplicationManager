import threading
import json
import time
import os
from watchdog.events import FileSystemEventHandler
import watchdog.observers

from src.manager.ram_logging.log_manager import LogManager

class MyHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.update_callback = callback

    def on_modified(self, event):
        self.update_callback("Hola")
        LogManager.logger.debug(f'event type: {event.event_type}  path : {event.src_path}')

class FileWatchdog(threading.Thread):
    def __init__(
        self,
        file,
        callback,
    ):
        super().__init__()
        # Create blank file
        if not os.path.exists(file): 
            with open(file, 'w') as f: 
                f.write("") 
        event_handler = MyHandler(callback)
        self.observer = watchdog.observers.Observer()
        self.observer.schedule(event_handler, path=file)
        self.observer.start()
        self._stop = threading.Event()
        LogManager.logger.info("Server Launched")

    def run(self) -> None:
        try:
            while not self._stop.isSet():
                time.sleep(1/30)
                return
        except Exception as ex:
            LogManager.logger.exception(ex)

    def stop(self) -> None:
        self._stop.set()
        self.observer.stop()
        self.observer.join()

    def send(self, data):
        pass
