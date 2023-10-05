from src.manager.manager.launcher.launcher_interface import ILauncher
from src.manager.manager.docker_thread.docker_thread import DockerThread
from src.manager.manager.vnc.vnc_server import Vnc_server
import time
import os
import stat
from typing import List, Any


class LauncherGazeboXserver(ILauncher):
    exercise_id: str
    display: str
    running: bool = False
    threads: List[Any] = []

    def run(self, callback):
        DRI_PATH = os.path.join(
            "/dev/dri", os.environ.get("DRI_NAME", "card0"))
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)        

        xserver_cmd = f"/usr/bin/Xorg -quiet -noreset +extension GLX +extension RANDR +extension RENDER -logfile ./xdummy.log -config ./xorg.conf {self.display}"
        xserver_thread = DockerThread(xserver_cmd)
        xserver_thread.start()
        self.threads.append(xserver_thread)

        self.running = True

    def check_device(self, device_path):
        try:
            return stat.S_ISCHR(os.lstat(device_path)[stat.ST_MODE])
        except:
            return False

    def is_running(self):
        return self.running

    def terminate(self):
        for thread in self.threads:
            thread.terminate()
            thread.join()
        self.running = False

    def died(self):
        pass