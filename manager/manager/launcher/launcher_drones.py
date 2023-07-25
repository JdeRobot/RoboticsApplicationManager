import os
import subprocess
from src.manager.manager.launcher.launcher_interface import ILauncher, LauncherException
from typing import List, Any
import psutil

class LauncherDrones(ILauncher):
    exercise_id: str
    type: str
    module: str
    parameters: List[str]
    launch_file: str
    process: Any = None

    def run(self, callback: callable = None):
        self.launch_file = os.path.expandvars(self.launch_file)
        self.process = subprocess.Popen(['python3', self.launch_file] + self.parameters)

        if self.process.poll() is not None:
            raise LauncherException("Exception launching Python script")

    def is_running(self):
        return self.process.poll() is None

    def terminate(self):
        if self.process is not None and self.is_running():
            parent = psutil.Process(self.process.pid)
            for child in parent.children(recursive=True):  # or parent.children() for recursive=False
                child.terminate()
            self.process.terminate()
            self.process.wait()

    def died(self):
        pass
