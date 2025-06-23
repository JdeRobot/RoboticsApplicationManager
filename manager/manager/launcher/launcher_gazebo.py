import sys
from manager.manager.launcher.launcher_interface import ILauncher
from manager.manager.docker_thread.docker_thread import DockerThread
from manager.manager.vnc.vnc_server import Vnc_server
from manager.libs.process_utils import (
    wait_for_process_to_start,
    check_gpu_acceleration,
)
import subprocess
import time
import os
import stat
from typing import List, Any


def call_service(self, service, service_type, request_data="{}"):
    command = f"ros2 service call {service} {service_type} '{request_data}'"
    subprocess.call(
        f"{command}",
        shell=True,
        stdout=sys.stdout,
        stderr=subprocess.STDOUT,
        bufsize=1024,
        universal_newlines=True,
    )


class LauncherGazebo(ILauncher):
    display: str
    internal_port: int
    external_port: int
    height: int
    width: int
    running: bool = False
    acceptsMsgs: bool = False
    threads: List[Any] = []
    gz_vnc: Any = Vnc_server()

    def run(self, config_file, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        # Configure browser screen width and height for gzclient
        gzclient_config_cmds = f"echo [geometry] > ~/.gazebo/gui.ini; echo x=0 >> ~/.gazebo/gui.ini; echo y=0 >> ~/.gazebo/gui.ini; echo width={self.width} >> ~/.gazebo/gui.ini; echo height={self.height} >> ~/.gazebo/gui.ini;"

        if ACCELERATION_ENABLED:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            # Write display config and start gzclient
            gzclient_cmd = f"export DISPLAY={self.display}; {gzclient_config_cmds} export VGL_DISPLAY={DRI_PATH}; vglrun gzclient --verbose"
        else:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc(self.display, self.internal_port, self.external_port)
            # Write display config and start gzclient
            gzclient_cmd = f"export DISPLAY={self.display}; {gzclient_config_cmds} gzclient --verbose"

        gzclient_thread = DockerThread(gzclient_cmd)
        gzclient_thread.start()
        self.threads.append(gzclient_thread)

        process_name = "gzclient"
        wait_for_process_to_start(process_name, timeout=60)

        self.running = True

    def pause(self):
        call_service("/pause_physics", "std_srvs/srv/Empty")

    def unpause(self):
        call_service("/unpause_physics", "std_srvs/srv/Empty")

    def reset(self):
        call_service("/reset_world", "std_srvs/srv/Empty")

    def is_running(self):
        return self.running

    def terminate(self):
        self.gz_vnc.terminate()
        for thread in self.threads:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
        self.running = False

    def died(self):
        pass
