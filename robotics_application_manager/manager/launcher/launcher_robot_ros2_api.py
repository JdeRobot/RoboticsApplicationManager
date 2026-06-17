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
import sys

import logging
from robotics_application_manager import LogManager
from gz.transport13 import Node

from gz.msgs10.empty_pb2 import Empty
from gz.msgs10.scene_pb2 import Scene


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
    except:
        p.kill()

        LogManager.logger.exception(f"Unable to complete call: {service}")
        raise Exception(f"Unable to complete call: {service}")


class LauncherRobotRos2Api(ILauncher):
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []

    def run(self, entity, robot_pose, extra_config, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        xserver_cmd = f"/usr/bin/Xorg -quiet -noreset +extension GLX +extension RANDR +extension RENDER -logfile ./xdummy.log -config ./xorg.conf :0"
        xserver_thread = DockerThread(xserver_cmd)
        xserver_thread.start()
        self.threads.append(xserver_thread)

        x, y, z, R, P, Y = robot_pose

        if extra_config == "None":
            extra_config = ""

        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} {extra_config}"
        else:
            exercise_launch_cmd = f"ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} {extra_config}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()

        # Wait until robot entity has spawned
        node = Node()
        spawned = False
        while not spawned:
            a = node.request(
                f"/world/default/scene/info",
                Empty(),
                Empty,
                Scene,
                1000,
            )
            if a[0]:
                for model in a[1].model:
                    if model.name == entity:
                        spawned = True
                        LogManager.logger.info("Robot spawned OK")

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

        cmd = kill_cmd + "bridge"
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
