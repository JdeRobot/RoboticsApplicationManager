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
        """Start the robot's launch WITHOUT blocking on spawn.

        This only fires the ros2 launch (async, in its own process) and returns
        immediately. Call wait_spawned() afterwards to block until the entity
        actually appears. Splitting it in two lets the manager start every
        robot's launch first and then wait for them all together, so N robots
        spawn in parallel (~one spawn time, not N) - which also makes every
        reset ~N times faster, since reset respawns the whole group.
        """
        self.entity = entity

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

        # pass the entity name too — multi-robot launch files use it as the
        # ROS/gz namespace so N robots don't collide on topics/node names.
        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} entity:={entity} {extra_config}"
        else:
            exercise_launch_cmd = f"ros2 launch {self.launch_file} x:={x} y:={y} z:={z} R:={R} P:={P} Y:={Y} entity:={entity} {extra_config}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()

    def wait_spawned(self, timeout=90):
        """Block until this robot's entity shows up in the gazebo scene.

        Runs on the caller's (main) thread on purpose: gz Node.request is a
        blocking call, so polling it from worker threads starves the GIL and
        hangs - that's exactly what broke the earlier threaded spawn attempt.
        The timeout stops a robot that never spawns from blocking forever.
        """
        node = Node()
        start = time.time()
        while time.time() - start < timeout:
            a = node.request(
                "/world/default/scene/info",
                Empty(),
                Empty,
                Scene,
                1000,
            )
            if a[0]:
                for model in a[1].model:
                    if model.name == self.entity:
                        LogManager.logger.info(f"Robot '{self.entity}' spawned OK")
                        return True
        LogManager.logger.error(
            f"Robot '{self.entity}' did not spawn within {timeout}s"
        )
        return False

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
