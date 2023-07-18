import os
from typing import List, Any
import time
import stat

from src.manager.manager.launcher.launcher_interface import ILauncher, LauncherException
from src.manager.manager.docker_thread.docker_thread import DockerThread
import subprocess

import logging

class LauncherRos2Api(ILauncher):
    exercise_id: str
    type: str
    module: str
    resource_folders: List[str]
    model_folders: List[str]
    plugin_folders: List[str]
    parameters: List[str]
    launch_file: str
    running = False

    def run(self,callback):
        DRI_PATH = os.path.join("/dev/dri", os.environ.get("DRI_NAME", "card0"))
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        logging.getLogger("roslaunch").setLevel(logging.CRITICAL)

        # expand variables in configuration paths
        launch_file = os.path.expandvars(self.launch_file)

        if (ACCELERATION_ENABLED):
            exercise_launch_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun ros2 launch {launch_file}"
        else:
            exercise_launch_cmd = f"ros2 launch {launch_file}"

        exercise_launch_thread = DockerThread(exercise_launch_cmd)
        exercise_launch_thread.start()

        self.running = True

    def is_running(self):
        return self.running
    
    def check_device(self, device_path):
        try:
            return stat.S_ISCHR(os.lstat(device_path)[stat.ST_MODE])
        except:
            return False

    def terminate(self):
        if self.is_running():
            kill_cmd = 'pkill -9 -f '
            cmd = kill_cmd + 'gzserver'
            subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, bufsize=1024, universal_newlines=True)
            cmd = kill_cmd + 'spawn_model.launch.py'
            subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, bufsize=1024, universal_newlines=True)
