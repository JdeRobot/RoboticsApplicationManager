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
import subprocess
from robotics_application_manager import LogManager
from gz.transport13 import Node
from gz.msgs10.empty_pb2 import Empty
from gz.msgs10.scene_pb2 import Scene
import logging


class LauncherRos2GzApi(ILauncher):
    type: str
    module: str
    launch_file: str
    threads: List[Any] = []

    def run(self, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        xserver_cmd = f"/usr/bin/Xorg -quiet -noreset +extension GLX +extension RANDR +extension RENDER -logfile ./xdummy.log -config ./xorg.conf :0"
        xserver_thread = DockerThread(xserver_cmd)
        xserver_thread.start()
        self.threads.append(xserver_thread)

        if ACCELERATION_ENABLED:
            exercise_launch_cmd = f"source /.env;export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {self.launch_file}"
        else:
            exercise_launch_cmd = f"source /.env;ros2 launch {self.launch_file}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()
        self.threads.append(exercise_launch_thread)

    def terminate(self):
        LogManager.logger.info(f"Terminating world launcher")
        for thread in self.threads[:]:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)

    def wait_robots_spawn(self, entities):
        # Wait until robots entities has spawned
        node = Node()
        missing_entities = entities
        while len(missing_entities) > 0:
            resp, output = node.request(
                f"/world/default/scene/info",
                Empty(),
                Empty,
                Scene,
                1000,
            )
            if resp:
                for model in output.model:
                    if model.name in missing_entities:
                        missing_entities.remove(model.name)
                        LogManager.logger.info(f"Robot ${model.name} spawned OK")
