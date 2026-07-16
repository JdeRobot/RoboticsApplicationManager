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
    entity: str = ""

    def run(self, entity, robot_pose, extra_config, callback):
        """Start the robot's launch. Does not wait for it to spawn.

        Only fires the ros2 launch (async, in its own process) and returns, so
        the manager can start every robot's launch first and then wait for them
        all together (see wait()). That way N robots spawn in parallel (~one
        spawn time, not N), which also makes every reset faster.
        """
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        self.entity = entity
        x, y, z, R, P, Y = robot_pose

        if extra_config == "None":
            extra_config = ""

        # Pass the entity name to the launch. Entity is the gazebo model name
        # (used to spawn and remove the model).
        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} entity:={entity} {extra_config}"
        else:
            exercise_launch_cmd = f"ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} entity:={entity} {extra_config}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()
        self.threads.append(exercise_launch_thread)

    def wait(self, entities, timeout=90):
        """Block until every entity in the list has appeared in the gazebo scene.

        One poll loop for the whole list, not one per robot: every launch was
        started first, so the robots spawn in parallel and each one is ticked
        off as it shows up. gz Node.request blocks, so this runs on the main
        thread (polling it from worker threads starves the GIL).
        """
        pending = set(entities)
        node = Node()
        start = time.time()
        while pending and time.time() - start < timeout:
            ok, scene = node.request(
                "/world/default/scene/info", Empty(), Empty, Scene, 1000
            )
            if ok:
                pending -= {model.name for model in scene.model}
        if pending:
            LogManager.logger.error(f"Robots did not spawn in time: {pending}")

    def terminate(self):
        LogManager.logger.info(f"Terminating robot launcher")
        for thread in self.threads[:]:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
