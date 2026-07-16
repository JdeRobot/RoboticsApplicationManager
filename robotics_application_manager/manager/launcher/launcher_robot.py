"""LauncherRobot module for managing robot launchers in different simulation worlds."""

import re
from typing import Optional
from pydantic import BaseModel

from robotics_application_manager.libs import (
    get_class,
    class_from_module,
    get_ros_version,
)
from robotics_application_manager import LogManager
from .launcher_interface import ILauncher

worlds = {
    "gz": {
        "2": [
            {
                "type": "gz",
                "module": "robot_ros2_api",
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
    entity: str = ""
    start_pose: Optional[list] = []

    @staticmethod
    def make_names_unique(robot_cfgs):
        """Rename only the robots whose names clash with an earlier one.

        The first robot to use a name keeps it; a later robot asking for the same
        name gets a numbered suffix:

            car, vehicle, car  ->  car, vehicle, car_1

        Entity and namespace are handled separately: a robot can have one and not
        the other, and a clash in one does not imply a clash in the other. Entity
        is a normal field, but namespace is not: it sits inside the extra_config
        string (e.g. "sensor:=camera namespace:=drone"), so we have to dig it out
        with a regex and write it back the same way.
        """
        for key in ("entity", "namespace"):
            used = set()
            for robot_cfg in robot_cfgs:
                if key == "entity":
                    name = robot_cfg.get("entity")
                else:
                    match = re.search(
                        r"namespace:=(\S+)", robot_cfg.get("extra_config", "")
                    )
                    name = match.group(1) if match else None

                if not name:
                    continue
                if name not in used:
                    used.add(name)
                    continue

                index = 1
                while f"{name}_{index}" in used:
                    index += 1
                new_name = f"{name}_{index}"

                if key == "entity":
                    robot_cfg["entity"] = new_name
                else:
                    robot_cfg["extra_config"] = re.sub(
                        r"namespace:=\S+",
                        f"namespace:={new_name}",
                        robot_cfg["extra_config"],
                    )
                used.add(new_name)

    def run(self, entity="", start_pose=None, extra_config=None):
        """Start the robot launcher. Does not wait for the robot to spawn."""
        self.entity = entity

        if start_pose is not None:
            self.start_pose = start_pose

        if extra_config is None:
            extra_config = ""

        for module in worlds[self.type][str(self.ros_version)]:
            module["launch_file"] = self.launch_file_path
            launcher = self.launch_module(module, extra_config)
            self.launchers.append(launcher)
        LogManager.logger.info(self.launchers)

    @staticmethod
    def wait_for(robot_launchers):
        """Wait until every robot in the list has spawned.

        Collects the entities of all the robots and checks them in a single
        poll loop, instead of waiting for one robot at a time. Entries with no
        launcher (a world with no robot assigned) are skipped.
        """
        launchers = [
            launcher
            for robot_launcher in robot_launchers
            if robot_launcher is not None
            for launcher in robot_launcher.launchers
        ]
        if not launchers:
            return
        # They are all the same simulator launcher, so any of them can run the
        # poll for the whole list of entities.
        launchers[0].wait([launcher.entity for launcher in launchers])

    def terminate(self):
        """Terminate all robot launchers and clear the launchers list."""
        LogManager.logger.info("Terminating robots launchers")
        if self.launchers:
            for launcher in self.launchers:
                launcher.terminate()
        self.launchers = []

    def launch_module(self, configuration, extra_config=None):
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

        launcher.run(self.entity, self.start_pose, extra_config, process_terminated)
        return launcher

    def launch_command(self, configuration):
        """Launch a robot command based on the provided configuration."""
        pass


class LauncherRobotException(Exception):
    """Exception class for errors related to LauncherRobot."""

    def __init__(self, message):
        """Initialize the LauncherRobotException with a message."""
        super(LauncherRobotException, self).__init__(message)
