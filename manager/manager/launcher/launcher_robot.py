"""LauncherRobot module for managing robot launchers in different simulation worlds."""

from typing import Optional
from pydantic import BaseModel

from manager.libs.process_utils import get_class, class_from_module, get_ros_version
from manager.ram_logging.log_manager import LogManager
from manager.manager.launcher.launcher_interface import ILauncher

worlds = {
    "gazebo": {
        "1": [
            {
                "type": "module",
                "module": "ros_api",
                "parameters": [],
                "launch_file": [],
            }
        ],
        "2": [
            {
                "type": "module",
                "module": "robot_ros2_api",
                "parameters": [],
                "launch_file": [],
            }
        ],
    },
    "drones": {
        "1": [
            {
                "type": "module",
                "module": "drones",
                "resource_folders": [],
                "model_folders": [],
                "plugin_folders": [],
                "parameters": [],
                "launch_file": [],
            }
        ],
        "2": [
            {
                "type": "module",
                "module": "drones_ros2",
                "resource_folders": [],
                "model_folders": [],
                "plugin_folders": [],
                "parameters": [],
                "launch_file": [],
            }
        ],
    },
    "gzsimdrones": {
        "2": [
            {
                "type": "module",
                "module": "drones_gzsim",
                "resource_folders": [],
                "model_folders": [],
                "plugin_folders": [],
                "parameters": [],
                "launch_file": [],
            }
        ],
    },
    "physical": {},
}


class LauncherRobot(BaseModel):
    """Class for managing robot launchers in different simulation worlds."""

    type: str
    launch_file_path: str
    module: str = ".".join(__name__.split(".")[:-1])
    ros_version: int = get_ros_version()
    launchers: Optional[ILauncher] = []
    start_pose: Optional[list] = []

    def run(self, start_pose=None):
        """Run the robot launcher with an optional start pose."""
        if start_pose is not None:
            self.start_pose = start_pose
        for module in worlds[self.type][str(self.ros_version)]:
            module["launch_file"] = self.launch_file_path
            launcher = self.launch_module(module)
            self.launchers.append(launcher)
        LogManager.logger.info(self.launchers)

    def terminate(self):
        """Terminate all robot launchers and clear the launchers list."""
        LogManager.logger.info("Terminating robot launcher")
        if self.launchers:
            for launcher in self.launchers:
                launcher.terminate()
        self.launchers = []

    def launch_module(self, configuration):
        """Launch a robot module based on the provided configuration."""

        def process_terminated(name, exit_code):
            LogManager.logger.info(
                f"LauncherEngine: {name} exited with code {exit_code}"
            )
            if self.terminated_callback is not None:
                self.terminated_callback(name, exit_code)

        launcher_module_name = configuration["module"]
        launcher_module = (
            f"{self.module}.launcher_{launcher_module_name}."
            f"Launcher{class_from_module(launcher_module_name)}"
        )
        launcher_class = get_class(launcher_module)
        launcher = launcher_class.from_config(launcher_class, configuration)

        launcher.run(self.start_pose, process_terminated)
        return launcher

    def launch_command(self, configuration):
        """Launch a robot command based on the provided configuration."""
        pass


class LauncherRobotException(Exception):
    """Exception class for errors related to LauncherRobot."""

    def __init__(self, message):
        """Initialize the LauncherRobotException with a message."""
        super(LauncherRobotException, self).__init__(message)
