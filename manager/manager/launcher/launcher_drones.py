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
            # Termina el grupo de procesos del proceso principal
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait()

    def died(self):
        pass
