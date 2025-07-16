"""
This module provides the LauncherVisualization class.

Responsible for managing visualization launchers in the Robotics Application Manager.
"""

from manager.libs.process_utils import get_class, class_from_module
from typing import Optional
from pydantic import BaseModel


from manager.manager.launcher.launcher_world import LauncherWorldException
from manager.ram_logging.log_manager import LogManager
from manager.manager.launcher.launcher_interface import ILauncher


visualization = {
    "none": [],
    "console": [
        {
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        }
    ],
    "bt_studio": [
        {
            "type": "module",
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "gazebo_view",
            "display": ":2",
            "external_port": 6080,
            "internal_port": 5900,
        },
    ],
    "bt_studio_gz": [
        {
            "type": "module",
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "gzsim_view",
            "display": ":2",
            "external_port": 6080,
            "internal_port": 5900,
        },
    ],
    "gazebo_gra": [
        {
            "type": "module",
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "gazebo_view",
            "display": ":2",
            "external_port": 6080,
            "internal_port": 5900,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "robot_display_view",
            "display": ":3",
            "external_port": 2303,
            "internal_port": 5902,
        },
    ],
    "gazebo_rae": [
        {
            "type": "module",
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "gazebo_view",
            "display": ":2",
            "external_port": 6080,
            "internal_port": 5900,
        },
    ],
    "gzsim_gra": [
        {
            "type": "module",
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "gzsim_view",
            "display": ":2",
            "external_port": 6080,
            "internal_port": 5900,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "robot_display_view",
            "display": ":3",
            "external_port": 2303,
            "internal_port": 5902,
        },
    ],
    "gzsim_rae": [
        {
            "type": "module",
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "gzsim_view",
            "display": ":2",
            "external_port": 6080,
            "internal_port": 5900,
        },
    ],
    "physic_gra": [
        {
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "robot_display_view",
            "display": ":2",
            "external_port": 2303,
            "internal_port": 5902,
        },
    ],
    "physic_rae": [
        {
            "module": "console",
            "display": ":1",
            "external_port": 1108,
            "internal_port": 5901,
        },
        {
            "type": "module",
            "width": 1024,
            "height": 768,
            "module": "robot_display_view",
            "display": ":2",
            "external_port": 2303,
            "internal_port": 5902,
        },
    ],
}


class LauncherVisualization(BaseModel):
    """Manages the launching and termination of visualization modules for the RAM."""

    module: str = ".".join(__name__.split(".")[:-1])
    visualization: str
    visualization_config_path: Optional[str] = None
    launchers: Optional[ILauncher] = []

    def run(self):
        """Launch all visualization modules specified in the configuration."""
        for module in visualization[self.visualization]:
            launcher = self.launch_module(module)
            self.launchers.append(launcher)

    def terminate(self):
        """Terminate all running visualization launchers."""
        LogManager.logger.info("Terminating visualization launcher")
        for launcher in self.launchers:
            if launcher.is_running():
                launcher.terminate()
        self.launchers = []

    def launch_module(self, configuration):
        """
        Launch a visualization module based on the provided configuration.

        Args:
            configuration (dict): Config dictionary for the visualization module.

        Returns:
            ILauncher: The launcher instance for the visualization module.
        """
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
        launcher.run(self.visualization_config_path, process_terminated)
        return launcher

    def launch_command(self, configuration):
        """
        Launch a visualization command.

        Args:
            configuration (dict): Config dictionary for the visualization command.
        """
        pass


class LauncherVisualizationException(Exception):
    """Exception raised for errors in the LauncherVisualization."""

    def __init__(self, message):
        """
        Initialize the LauncherVisualizationException with an error message.

        Args:
            message (str): The error message describing the exception.
        """
        super(LauncherWorldException, self).__init__(message)
