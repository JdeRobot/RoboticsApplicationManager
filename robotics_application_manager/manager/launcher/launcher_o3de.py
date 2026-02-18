import sys
from .launcher_interface import ILauncher
from robotics_application_manager.manager.docker_thread import DockerThread
from robotics_application_manager.manager.vnc import Vnc_server
from robotics_application_manager.libs import (
    wait_for_process_to_start,
    check_gpu_acceleration,
)
import subprocess
import time
import os
import stat
from typing import List, Any
from robotics_application_manager import LogManager


class LauncherO3de(ILauncher):
    running: bool = False
    threads: List[Any] = []
    acceptsMsgs: bool = False
    gz_vnc: Any = Vnc_server()

    def run(self, config_file, callback):

        # process_name = "gz sim"
        # wait_for_process_to_start(process_name, timeout=60)

        self.running = True

    def check_device(self, device_path):
        try:
            return stat.S_ISCHR(os.lstat(device_path)[stat.ST_MODE])
        except:
            return False

    def is_running(self):
        return self.running

    def terminate(self):
        self.running = False

    def died(self):
        pass

    def pause(self):
        self.running = False
        pass

    def unpause(self):
        self.running = True
        pass

    def reset(self):
        # TODO: add reset
        pass

    def get_dri_path(self):
        directory_path = "/dev/dri"
        dri_path = ""
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            files = os.listdir(directory_path)
            if "card1" in files:
                dri_path = os.path.join("/dev/dri", os.environ.get("DRI_NAME", "card1"))
            else:
                dri_path = os.path.join("/dev/dri", os.environ.get("DRI_NAME", "card0"))
        return dri_path
