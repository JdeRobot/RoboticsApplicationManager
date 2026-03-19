import os
from typing import List, Any
import time
import stat

from .launcher_interface import (
    ILauncher,
    LauncherException,
)
from robotics_application_manager.manager.docker_thread import DockerThread
import subprocess

import logging


class LauncherRobotRos2Api(ILauncher):
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []

    def run(self, robot_pose, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        xserver_cmd = f"/usr/bin/Xorg -quiet -noreset +extension GLX +extension RANDR +extension RENDER -logfile ./xdummy.log -config ./xorg.conf :0"
        xserver_thread = DockerThread(xserver_cmd)
        xserver_thread.start()
        self.threads.append(xserver_thread)

        ROBOT_POSE = f"ROBOT_X={robot_pose[0]} ROBOT_Y={robot_pose[1]} ROBOT_Z={robot_pose[2]} ROBOT_ROLL={robot_pose[3]} ROBOT_PITCH={robot_pose[4]} ROBOT_YAW={robot_pose[5]}"

        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun {ROBOT_POSE} ros2 launch {self.launch_file}"
        else:
            exercise_launch_cmd = f"{ROBOT_POSE} ros2 launch {self.launch_file}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()

    def terminate(self):
        if self.threads is not None:
            for thread in self.threads:
                if thread.is_alive():
                    thread.terminate()
                    thread.join()
                self.threads.remove(thread)

        kill_cmd = "pkill -9 -f "
        cmd = kill_cmd + "spawn_robot.launch.py"
        subprocess.call(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            bufsize=1024,
            universal_newlines=True,
        )

        kill_cmd = "pkill -9 "
        cmd = kill_cmd + "bridg"
        subprocess.call(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            bufsize=1024,
            universal_newlines=True,
        )

        cmd = kill_cmd + "robot_state_publisher"
        subprocess.call(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            bufsize=1024,
            universal_newlines=True,
        )
