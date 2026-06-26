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


class LauncherRobotRos2Api(ILauncher):
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []

    def run(self, entity, robot_pose, extra_config, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        x, y, z, R, P, Y = robot_pose

        if extra_config == "None":
            extra_config = ""

        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} {extra_config}"
        else:
            exercise_launch_cmd = f"ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} {extra_config}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()
        self.threads.append(exercise_launch_thread)

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
        LogManager.logger.info(f"Terminating robot launcher")
        for thread in self.threads[:]:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
