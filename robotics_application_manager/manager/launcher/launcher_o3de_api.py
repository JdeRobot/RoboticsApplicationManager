import os
import sys
from typing import List, Any
import time
import stat

from .launcher_interface import (
    ILauncher,
    LauncherException,
)
from robotics_application_manager.manager.docker_thread import DockerThread
from robotics_application_manager.manager.vnc import Vnc_server
from robotics_application_manager.libs import (
    wait_for_process_to_start,
    check_gpu_acceleration,
)
import subprocess

import logging


class LauncherO3deApi(ILauncher):
    display: str
    internal_port: int
    external_port: int
    height: int
    width: int
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []
    gz_vnc: Any = Vnc_server()

    def run(self, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        # TODO: add run here

        xserver_cmd = f"/usr/bin/Xorg -quiet -noreset +extension GLX +extension RANDR +extension RENDER -logfile ./xdummy.log -config ./xorg.conf :0"
        xserver_thread = DockerThread(xserver_cmd)
        xserver_thread.start()
        self.threads.append(xserver_thread)

        if ACCELERATION_ENABLED:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            # Write display config
            o3decmd = f'export DISPLAY={self.display}; data/workspace/o3de/gme_o3de/bin/Linux/release/Monolithic/MySimulationProject2.GameLauncher +LoadLevel "{self.launch_file}" --forceAdapter="NVIDIA"'
        else:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc(self.display, self.internal_port, self.external_port)
            # Write display config
            o3decmd = f'export DISPLAY={self.display}; data/workspace/o3de/gme_o3de/bin/Linux/release/Monolithic/MySimulationProject2.GameLauncher +LoadLevel "{self.launch_file}" --forceAdapter="NVIDIA"'

        gzclient_thread = DockerThread(o3decmd)
        gzclient_thread.start()
        self.threads.append(gzclient_thread)

        process_name = "MySimulationProject2.GameLauncher"
        wait_for_process_to_start(process_name, timeout=360)

    def terminate(self):
        self.gz_vnc.terminate()
        if self.threads is not None:
            for thread in self.threads:
                if thread.is_alive():
                    thread.terminate()
                    thread.join()
                self.threads.remove(thread)

        # TODO: processes to kill
        to_kill = ["MySimulationProject2.GameLauncher"]

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
