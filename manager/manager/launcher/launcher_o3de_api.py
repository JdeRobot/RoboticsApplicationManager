import os
import sys
from typing import List, Any
import time
import stat

from manager.manager.launcher.launcher_interface import ILauncher, LauncherException
from manager.manager.docker_thread.docker_thread import DockerThread
import subprocess

import logging


class LauncherO3deApi(ILauncher):
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []

    def run(self, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        #TODO: add run here

    def terminate(self):
        if self.threads is not None:
            for thread in self.threads:
                if thread.is_alive():
                    thread.terminate()
                    thread.join()
                self.threads.remove(thread)

        # TODO: processes to kill
        to_kill = ["launch.py"]

        kill_cmd = "pkill -9 -f "
        for i in to_kill:
            cmd = kill_cmd + i
            subprocess.call(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                bufsize=1024,
                universal_newlines=True,
            )
