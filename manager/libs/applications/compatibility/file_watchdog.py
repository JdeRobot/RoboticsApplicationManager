import threading
import time
import os
from watchdog.events import FileSystemEventHandler
import watchdog.observers

from src.manager.ram_logging.log_manager import LogManager

class Handler(FileSystemEventHandler):
    
    def __init__(self, file, callback):
        self.update_callback = callback
        self.file = file
        self.hash = None
 
    def on_modified(self, event):
        if event.event_type == 'modified':
            with open(self.file, 'r') as f: 
                data = f.read() 
            if self.hash is None or self.hash != hash(data):
                self.hash = hash(data)
                self.update_callback(data)

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
        event_handler = Handler(file, callback)
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
