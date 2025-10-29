import os
import sys
from typing import List, Any
import time
import stat

from manager.manager.launcher.launcher_interface import ILauncher, LauncherException
from manager.manager.docker_thread.docker_thread import DockerThread
from manager.manager.vnc.vnc_server import Vnc_server
from manager.libs.process_utils import (
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

        #TODO: add run here

        xserver_cmd = f"/usr/bin/Xorg -quiet -noreset +extension GLX +extension RANDR +extension RENDER -logfile ./xdummy.log -config ./xorg.conf :0"
        xserver_thread = DockerThread(xserver_cmd)
        xserver_thread.start()
        self.threads.append(xserver_thread)
        
        LevelSelect=f'echo "LoadLevel Levels/{self.launch_file}" > data/workspace/ROS2Demo/autoexec.cfg'
        
        LevelSelect_thread = DockerThread(LevelSelect)
        LevelSelect_thread.start()
        self.threads.append(LevelSelect_thread)
        
        if ACCELERATION_ENABLED:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            # Write display config
            o3decmd = f'export DISPLAY={self.display}; data/workspace/ROS2Demo/build/linux/bin/profile/ROS2Demo.GameLauncher --forceAdapter="NVIDIA"'
        else:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc(self.display, self.internal_port, self.external_port)
            # Write display config
            o3decmd = f'export DISPLAY={self.display}; data/workspace/ROS2Demo/build/linux/bin/profile/ROS2Demo.GameLauncher --forceAdapter="NVIDIA"'

        gzclient_thread = DockerThread(o3decmd)
        gzclient_thread.start()
        self.threads.append(gzclient_thread)

        process_name = 'ROS2Demo.GameLauncher'
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
        to_kill = ["ROS2Demo.GameLauncher"]

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
