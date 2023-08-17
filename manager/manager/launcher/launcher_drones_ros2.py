import os
import subprocess
from src.manager.manager.launcher.launcher_interface import ILauncher, LauncherException
from src.manager.manager.docker_thread.docker_thread import DockerThread
from typing import List, Any
import time

class LauncherDronesRos2(ILauncher):
    exercise_id: str
    type: str
    module: str
    resource_folders: List[str]
    model_folders: List[str]
    plugin_folders: List[str]
    world_file: str
    running = False
    threads: List[Any] = []

    def run(self, callback):

        # expand variables in configuration paths
        self._set_environment()
        world_file = os.path.expandvars(self.world_file)

        # Launching MicroXRCE and Aerostack2 nodes
        as2_launch_cmd = f"ros2 launch jderobot_drones as2_default_classic_gazebo.launch.py world_file:={world_file}"

        as2_launch_thread = DockerThread(as2_launch_cmd)
        as2_launch_thread.start()
        self.threads.append(as2_launch_thread)

        # Launching gzserver and PX4
        px4_launch_cmd = f"$AS2_GZ_ASSETS_SCRIPT_PATH/default_run.sh {world_file}"

        px4_launch_thread = DockerThread(px4_launch_cmd)
        px4_launch_thread.start()
        self.threads.append(px4_launch_thread)

        self.running = True

    def is_running(self):
        return True

    def terminate(self):
        if self.is_running():
            for thread in self.threads:
                thread.terminate()
                thread.join()
            self.running = False

    def _set_environment(self):
        resource_folders = [os.path.expandvars(path) for path in self.resource_folders]
        model_folders = [os.path.expandvars(path) for path in self.model_folders]
        plugin_folders = [os.path.expandvars(path) for path in self.plugin_folders]

        os.environ["GAZEBO_RESOURCE_PATH"] = f"{os.environ.get('GAZEBO_RESOURCE_PATH', '')}:{':'.join(resource_folders)}"
        os.environ["GAZEBO_MODEL_PATH"] = f"{os.environ.get('GAZEBO_MODEL_PATH', '')}:{':'.join(model_folders)}"
        os.environ["GAZEBO_PLUGIN_PATH"] = f"{os.environ.get('GAZEBO_PLUGIN_PATH', '')}:{':'.join(plugin_folders)}"
