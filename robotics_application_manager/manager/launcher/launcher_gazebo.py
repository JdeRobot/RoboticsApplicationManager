"""
Gazebo Classic Launcher and Lifecycle Manager.

Handles the initialization, state management, and cleanup of the
Gazebo GUI client (gzclient). Orchestrates display routing via
VNC and provides hardware-accelerated rendering through VirtualGL
when compatible DRI devices are detected.
"""

import sys
from .launcher_interface import ILauncher
from robotics_application_manager.manager.docker_thread import DockerThread
from robotics_application_manager.manager.vnc import Vnc_server
from robotics_application_manager.libs import (
    wait_for_process_to_start,
)
import subprocess
from typing import List, Any
from robotics_application_manager import LogManager


def call_service(service, service_type, request_data="{}"):
    command = f"ros2 service call {service} {service_type} '{request_data}'"
    try:
        p = subprocess.Popen(
            [
                f"{command}",
            ],
            shell=True,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            bufsize=1024,
            universal_newlines=True,
        )
        p.wait(10)
    except subprocess.TimeoutExpired as e:
        p.kill()

        LogManager.logger.exception(f"Unable to complete call: {service}")
        raise e


class LauncherGazebo(ILauncher):
    """
    Orchestrator for Gazebo simulation visualization.

    Manages the 'gzclient' lifecycle, including resolution configuration,
    X11 display mapping, and background thread monitoring.
    """

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
        """
        Launches the Gazebo client with appropriate display settings.

        Checks for hardware acceleration support (DRI) and initializes the
        VNC server. Dynamically generates a 'gui.ini' file to ensure the
        simulation resolution matches the web frontend dimensions.

        Args:
            config_file (str): Path to the exercise configuration.
            callback (function): Completion or state-change callback.
        """
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
        """Suspends the physics engine via the /pause_physics ROS 2 service."""
        call_service("/pause_physics", "std_srvs/srv/Empty")

    def unpause(self):
        """Resumes the physics engine via the /unpause_physics ROS 2 service."""
        call_service("/unpause_physics", "std_srvs/srv/Empty")

    def reset(self, robot_entity=None):
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
