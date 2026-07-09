import os
from typing import List, Any
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


class LauncherRobotRos2Api(ILauncher):
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []

    def run(self, entity, robot_pose, extra_config, callback):
        """Start the robot's launch (does not wait for it to spawn).

        Only fires the ros2 launch (async, in its own process) and returns. The
        manager starts every robot's launch first and then waits for them all to
        appear in the scene together, so N robots spawn in parallel (~one spawn
        time, not N) - which also makes every reset faster, since reset respawns
        the whole group.
        """
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        x, y, z, R, P, Y = robot_pose

        if extra_config == "None":
            extra_config = ""

        # pass the entity name to the launch. entity is the gazebo model name
        # (used to spawn/remove the model)
        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} entity:={entity} {extra_config}"
        else:
            exercise_launch_cmd = f"ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} entity:={entity} {extra_config}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()
        self.threads.append(exercise_launch_thread)

    def terminate(self):
        LogManager.logger.info(f"Terminating robot launcher")
        for thread in self.threads[:]:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
