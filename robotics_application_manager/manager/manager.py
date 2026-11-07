"""Manager module for Robotics Application Manager.

This module defines the Manager class and related logic for managing applications,
including launching worlds, robots, visualizations,
and handling code analysis and formatting.
"""

import sys

sys.path.insert(0, "/RoboticsApplicationManager")

import json
import tempfile
import black
import os
import signal
import subprocess
import re
import psutil
import shutil
import time
import base64
import zipfile
import jedi
import traceback
import asyncio

from queue import Queue
from uuid import uuid4
from transitions.extensions import AsyncMachine
from robotics_application_manager.comms import (
    ManagerConsumerMessageException,
    ManagerConsumerMessage,
    ManagerConsumer,
)
from robotics_application_manager.libs import (
    check_gpu_acceleration,
    get_class_from_file,
    stop_process_and_children,
    ConfigurationManager,
)
from robotics_application_manager.ram_logging import LogManager
from robotics_application_manager.manager.launcher import (
    LauncherScene,
    LauncherRobot,
    LauncherTools,
)
from robotics_application_manager.manager.lint import Lint
from robotics_application_manager.manager.editor import serialize_completions


class Manager:
    """
    Manager class for Robotics Application Manager.

    This class manages the lifecycle of robotics applications,
    including launching worlds, robots, visualizations,
    handling code analysis, formatting, and communication with clients.
    """

    states = [
        "idle",
        "connected",
        "world_ready",
        "tools_ready",
        "application_running",
        "paused",
    ]

    transitions = [
        # Transitions for state idle
        {
            "trigger": "connect",
            "source": "idle",
            "dest": "connected",
            "before": "on_connect",
        },
        # Transitions for state connected
        {
            "trigger": "launch_world",
            "source": "connected",
            "dest": "world_ready",
            "before": "on_launch_world",
        },
        # Transitions for state world ready
        {
            "trigger": "prepare_tools",
            "source": "world_ready",
            "dest": "tools_ready",
            "before": "on_prepare_tools",
        },
        # Transitions for state tools_ready
        {
            "trigger": "run_application",
            "source": ["tools_ready", "paused", "application_running"],
            "dest": "application_running",
            "before": "on_run_application",
        },
        # Transitions for state application_running
        {
            "trigger": "pause",
            "source": "application_running",
            "dest": "paused",
            "before": "on_pause",
        },
        {
            "trigger": "resume",
            "source": "paused",
            "dest": "application_running",
            "before": "on_resume",
        },
        # Transitions for terminate levels
        {
            "trigger": "terminate_application",
            "source": ["tools_ready", "application_running", "paused"],
            "dest": "tools_ready",
            "before": "on_terminate_application",
        },
        {
            "trigger": "terminate_tools",
            "source": "tools_ready",
            "dest": "world_ready",
            "before": "on_terminate_tools",
        },
        {
            "trigger": "terminate_world",
            "source": "world_ready",
            "dest": "connected",
            "before": "on_terminate_world",
        },
        # Global transitions
        {
            "trigger": "disconnect",
            "source": "*",
            "dest": "idle",
            "before": "on_disconnect",
        },
        # Style check
        {
            "trigger": "style_check",
            "source": [
                "idle",
                "connected",
                "paused",
                "world_ready",
                "tools_ready",
            ],
            "dest": "=",
            "before": "on_style_check_application",
        },
    ]

    def __init__(self, host: str, port: int):
        """
        Initialize the Manager instance with the given host and port.

        This method sets up the state machine, initializes the ROS version,
        creates a message queue, and prepares the consumer for communication.
        Parameters:
            host (str): The host address to listen to.
            port (int): The port number to listen to.
        """
        self.machine = AsyncMachine(
            model=self,
            states=Manager.states,
            transitions=Manager.transitions,
            initial="idle",
            send_event=True,
            after_state_change=self.state_change,
        )
        self.ros_version = subprocess.check_output(["bash", "-c", "echo $ROS_DISTRO"])
        self.consumer = None
        self.scene_launcher = None
        self.world_type = None
        self.robot_launchers = []
        self.robot_configs = []
        self.tools_launcher = None
        self.application_processes = []
        self.running = True
        self.linter = Lint()
        self.host = host
        self.port = port

        # Creates workspace directories
        worlds_dir = "/workspace/worlds"
        code_dir = "/workspace/code"
        binaries_dir = "/workspace/binaries"
        if not os.path.isdir(worlds_dir):
            os.makedirs(worlds_dir)
        if not os.path.isdir(code_dir):
            os.makedirs(code_dir)
        if not os.path.isdir(binaries_dir):
            os.makedirs(binaries_dir)

    async def state_change(self, event):
        """
        Handle actions to be performed after a state change in the state machine.

        Parameters:
            event: The event object associated with the state change.
        """
        LogManager.logger.info(f"State changed to {self.state}")
        if self.consumer is not None:
            await self.consumer.send_message({"state": self.state}, command="state-changed")

    async def update(self, data):
        """
        Send an update message to the client with the provided data.

        Parameters:
            data: The data to be sent in the update message.
        """
        LogManager.logger.debug("Sending update to client")
        if self.consumer is not None:
            await self.consumer.send_message({"update": data}, command="update")

    async def update_bt_studio(self, data):
        """
        Send an update message to the client for BT Studio with the provided data.

        Parameters:
            data: The data to be sent in the update message.
        """
        LogManager.logger.debug("Sending update to client")
        if self.consumer is not None:
            await self.consumer.send_message({"update": data}, command="update")

    async def on_connect(self, event):
        """
        Triggered when the application transitions to the 'connected' state.

        It sends an introspection message to a consumer with key information.

        Parameters:
            event (Event): Event object containing data related to the 'connect' event.

        The message sent to the consumer includes:
        - `robotics_backend_version`: The current Robotics Backend version.
        - `ros_version`: The current ROS (Robot Operating System) distribution version.
        - `gpu_avaliable`: Boolean indicating whether GPU acceleration is available.
        """
        await self.consumer.send_message(
            {
                "robotics_backend_version": subprocess.check_output(
                    ["bash", "-c", "echo $IMAGE_TAG"]
                ),
                "ros_version": self.ros_version,
                "gpu_avaliable": check_gpu_acceleration(),
            },
            command="introspection",
        )

    async def on_launch_world(self, event):
        """
        Handle the 'launch' event, transitioning the application from 'connected' to 'ready' state.

        This method initializes the launch process based on the provided configuration.

        During the launch process, it validates and processes the configuration data received from the event.
        It then creates and starts a LauncherScene instance with the validated configuration.
        This setup is crucial for preparing the environment and resources necessary for the application's execution.

        Parameters:
            event (Event): The event object containing data related to the 'launch' event.
                        This data includes configuration information necessary for initializing the launch process.

        Raises:
            ValueError: If the configuration data is invalid or incomplete, a ValueError is raised,
                        indicating the issue with the provided configuration.

        Note:
            The method logs the start of the launch transition and the configuration details for debugging and traceability.
        """
        cfg_dict = event.kwargs.get("data", {})
        scene_cfg = cfg_dict["scene"]
        robot_cfgs = cfg_dict["robot"]

        def make_unique(cfgs, key, param=None):
            new_values = set()

            for cfg in cfgs:
                new_val = cfg[key]
                if new_val is None:
                    continue

                if param is not None:
                    new_val = re.search(rf"{param}:=(\S+)", new_val)
                    if new_val is None:
                        continue
                    new_val = new_val.group(1)

                index = 1
                while new_val in new_values:
                    new_val = f"{new_val}_{index}"
                    index += 1

                if param is not None:
                    cfg[key] = re.sub(
                        rf"{param}:=\S+",
                        f"{param}:={new_val}",
                        cfg[key],
                    )
                else:
                    cfg[key] = new_val

                new_values.add(new_val)

        make_unique(robot_cfgs, "entity")
        make_unique(robot_cfgs, "extra_config", param="namespace")

        # Launch scene
        try:
            if scene_cfg["type"] == None:
                self.scene_launcher = None
                LogManager.logger.info("Launch transition finished")
                return
            cfg = ConfigurationManager.validate(scene_cfg)
            if "zip" in scene_cfg:
                LogManager.logger.info("Launching scene from received zip")
                self.prepare_custom_world(scene_cfg)
            else:
                LogManager.logger.info("Launching scene from the RB")

            LogManager.logger.info(cfg)
        except ValueError as e:
            LogManager.logger.error(f"Configuration validation failed: {e}")

        self.world_type = scene_cfg["type"]

        self.scene_launcher = LauncherScene(**cfg.model_dump())
        LogManager.logger.info(str(self.scene_launcher))

        # Launch robot
        self.robot_launchers = []
        self.robot_configs = []
        for robot_cfg in robot_cfgs:
            try:
                cfg = ConfigurationManager.validate(robot_cfg)
                LogManager.logger.info("Launching robot from the RB")
                LogManager.logger.info(cfg)
            except ValueError as e:
                LogManager.logger.error(f"Configuration validation failed: {e}")

            robot_launcher = LauncherRobot(**cfg.model_dump())
            self.robot_launchers.append(robot_launcher)
            self.robot_configs.append(robot_cfg)
            LogManager.logger.info(str(robot_launcher))

        await self.scene_launcher.run()

        robots_data = zip(self.robot_launchers, self.robot_configs)
        entities = []
        for launcher, cfg in robots_data:
            await launcher.run(cfg["entity"], cfg["start_pose"], cfg["extra_config"])
            entities.append(cfg["entity"])

        self.scene_launcher.wait_robots_spawn(entities)

        LogManager.logger.info("Launch transition finished")

    async def prepare_custom_world(self, cfg_dict):
        """
        Prepare and extract a custom world from a base64-encoded zip file.

        Then build it in the workspace.

        Parameters:
            cfg_dict (dict): Config dictionary containing the world name and zip data
        """
        # Unzip the app
        if cfg_dict["zip"].startswith("data:"):
            _, _, zip_file = cfg_dict["zip"].partition("base64,")
        else:
            zip_file = cfg_dict["zip"]

        world_ref = "/workspace/worlds/src/" + cfg_dict["name"]
        # Remove old content
        if os.path.exists("/workspace/worlds"):
            shutil.rmtree("/workspace/worlds", ignore_errors=False)

        # Create the folder if it doesn't exist
        world_folder = world_ref + "/"
        if not os.path.exists(world_folder):
            os.makedirs(world_folder)

        zip_destination = world_ref + ".zip"
        with open(zip_destination, "wb") as result:
            result.write(base64.b64decode(zip_file))

        zip_ref = zipfile.ZipFile(zip_destination, "r")
        zip_ref.extractall(world_folder + "/")
        zip_ref.close()

        os.system(
            '/bin/bash -c "cd /workspace/worlds; source /opt/ros/humble/setup.bash; colcon build --symlink-install; source install/setup.bash; cd ../.."'
        )

    async def on_prepare_tools(self, event):
        LogManager.logger.info("Tools transition started")
        cfg_dict = event.kwargs.get("data", {})
        tools = cfg_dict["tools"]
        config = cfg_dict["config"]

        self.tools_launcher = LauncherTools(
            world_type=self.world_type, tools=tools, tools_config=config
        )

        await self.tools_launcher.run(self.consumer)
        LogManager.logger.info("Tools transition finished")

    def write_to_tool_terminal(self, msg):
        """Search console in docker different of /dev/pts/0 ."""
        pts_consoles = [
            f"/dev/pts/{dev}" for dev in os.listdir("/dev/pts/") if dev.isdigit()
        ]
        consoles = []
        for console in pts_consoles:
            if console != "/dev/pts/0":
                try:
                    # Search if it's a console
                    with open(console, "w") as f:
                        f.write("")
                    consoles.append(console)
                except Exception:
                    # Continue searching
                    continue

        for i in consoles:
            with open(i, "w") as console:
                console.write(msg)

    async def on_run_application(self, event):
        """
        Handle the 'run_application' event.

        This method manages the process of running the user application,
        including preparing the code, handling console output,
        and launching the application process.

        Parameters:
            event: The event object containing application configuration and code data.
        """
        # Kill already running code
        for process in self.application_processes:
            try:
                proc = psutil.Process(process.pid)
                proc.suspend()
                proc.kill()
            except Exception:
                pass
        self.application_processes = []

        # Delete old files
        if os.path.exists("/workspace/code"):
            shutil.rmtree("/workspace/code", ignore_errors=False)
        os.mkdir("/workspace/code")

        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        entrypoints = app_cfg["entrypoint"]
        to_lint = app_cfg["linter"]

        # Unzip the app
        if app_cfg["code"].startswith("data:"):
            _, _, code = app_cfg["code"].partition("base64,")
        with open("/workspace/code/app.zip", "wb") as result:
            result.write(base64.b64decode(code))
        zip_ref = zipfile.ZipFile("/workspace/code/app.zip", "r")
        zip_ref.extractall("/workspace/code")
        zip_ref.close()

        fds = os.listdir("/dev/pts/")
        console_fd = str(max(map(int, fds[:-1])))

        # Pass the linter
        errors = self.linter.evaluate_source_code(to_lint)
        failed_linter = False

        for error in errors:
            if error != "":
                failed_linter = True
                self.write_to_tool_terminal(error + "\n\n")

        if failed_linter:
            raise Exception(errors)

        needs_compile = False

        for entrypoint in entrypoints:
            if entrypoint.endswith((".launch.py", ".cpp")):
                needs_compile = True
                break

        if needs_compile:
            compile_process = subprocess.Popen(
                [
                    "cd /workspace/code && source /opt/ros/lyrical/setup.bash && colcon build && source install/setup.bash && cd ../.."
                ],
                stdin=open("/dev/pts/" + console_fd, "r"),
                stdout=open("/dev/pts/" + console_fd, "w"),
                stderr=open("/dev/pts/" + console_fd, "w"),
                bufsize=1024,
                universal_newlines=True,
                shell=True,
                executable="/bin/bash",
            )
            returncode = compile_process.wait()
            if returncode != 0:
                # raise Exception("Failed to compile")
                LogManager.logger.info("Failed to compile")
                return

        for entrypoint in entrypoints:
            if not os.path.isfile(entrypoint):
                LogManager.logger.info("User code not found")
                raise Exception("User code not found")

            command = ["python3", entrypoint]
            executable = None
            shell = False

            if entrypoint.endswith(".launch.py"):
                command = [
                    f"source /workspace/code/install/setup.bash && ros2 launch {entrypoint}"
                ]
                executable = "/bin/bash"
                shell = True
            elif entrypoint.endswith(".cpp"):
                command = [
                    "source /workspace/code/install/setup.bash && ros2 run academy academyCode"
                ]
                executable = "/bin/bash"
                shell = True

            proc = subprocess.Popen(
                command,
                stdin=open("/dev/pts/" + console_fd, "r"),
                stdout=open("/dev/pts/" + console_fd, "w"),
                stderr=open("/dev/pts/" + console_fd, "w"),
                bufsize=1024,
                universal_newlines=True,
                shell=shell,
                executable=executable,
                start_new_session=True,
            )

            proc.send_signal(signal.SIGSTOP)
            self.application_processes.append(proc)

        self.unpause_sim()
        for app in self.application_processes:
            app.send_signal(signal.SIGCONT)

        LogManager.logger.info("Run application transition finished")

    async def on_terminate_application(self, event):
        """
        Handle the 'terminate_application' event.

        Terminates the currently running application process,
        pauses and resets the simulation if applicable.

        Parameters:
            event: The event object associated with the termination request.
        """
        for process in self.application_processes:
            try:
                stop_process_and_children(process)
            except Exception:
                LogManager.logger.exception("No application running")

        if len(self.application_processes) > 0:
            self.pause_sim()
            await self.reset_sim()
            self.application_processes = []

    async def on_terminate_tools(self, event):

        await self.tools_launcher.terminate()
        self.tools_launcher = None

    async def on_terminate_world(self, event):
        """
        Handle the 'terminate_world' event.

        Terminates the world and robot launchers if they exist
        and terminates related Harmonic processes.

        Parameters:
            event: The event object associated with the termination request.
        """
        if self.scene_launcher is not None:
            await self.scene_launcher.terminate()
            self.scene_launcher = None
            self.world_type = None

        for launcher in self.robot_launchers:
            await launcher.terminate()
        self.robot_launchers = []

    async def on_disconnect(self, event):
        """
        Handle the 'disconnect' event.

        This method stops all running processes,
        terminates launchers, and restarts the script.
        """
        LogManager.logger.info("-------------------Disconnecting--------------------------")
        try:
            for process in self.application_processes:
                stop_process_and_children(process)
            self.application_processes = []
        except Exception:
            LogManager.logger.exception("Exception stopping application process")

        if self.tools_launcher:
            try:
                await self.tools_launcher.terminate()
            except Exception as e:
                LogManager.logger.exception("Exception terminating tools launcher")

        try:
            for launcher in self.robot_launchers:
                await launcher.terminate()
            self.robot_launchers = []
        except Exception as e:
            LogManager.logger.exception("Exception terminating robot launcher")

        if self.scene_launcher:
            try:
                await self.scene_launcher.terminate()
            except Exception as e:
                LogManager.logger.exception("Exception terminating scene launcher")

    async def process_message(self, message):
        if message.command == "gui":
            if self.tools_launcher is not None:
                await self.tools_launcher.pass_msg(message.data)
            return

        await self.trigger(message.command, data=message.data or None)

        response = {"message": f"Exercise state changed to {self.state}"}
        await self.consumer.send_message(message.response(response))

    async def on_pause(self, msg):
        if len(self.application_processes) > 0:
            for process in self.application_processes:
                proc = psutil.Process(process.pid)
                children = proc.children(recursive=True)
                children.append(proc)
                for p in children:
                    try:
                        p.suspend()
                    except psutil.NoSuchProcess:
                        pass
            self.pause_sim()
        else:
            LogManager.logger.warning(
                "Application process was None during pause. Calling termination."
            )
            self.pause_sim()
            await self.reset_sim()

    async def on_resume(self, msg):
        """
        Resume the application process if it exists, otherwise reset the simulation.

        Parameters:
            msg: The event or message triggering the resume action.
        """
        if len(self.application_processes) > 0:
            for process in self.application_processes:
                proc = psutil.Process(process.pid)
                children = proc.children(recursive=True)
                children.append(proc)
                for p in children:
                    try:
                        p.resume()
                    except psutil.NoSuchProcess:
                        pass
            self.unpause_sim()
        else:
            LogManager.logger.warning(
                "Application process was None during resume. Calling termination."
            )
            await self.reset_sim()

    def pause_sim(self):
        try:
            self.tools_launcher.pause()
        except subprocess.TimeoutExpired as e:
            self.write_to_tool_terminal(f"{e}\n\n")
            raise Exception("Failed to pause simulator")

    def unpause_sim(self):
        try:
            self.tools_launcher.unpause()
        except subprocess.TimeoutExpired as e:
            self.write_to_tool_terminal(f"{e}\n\n")
            raise Exception("Failed to start simulator")

    async def reset_sim(self):
        """
        Reset the simulation environment and relaunch the robot if applicable.

        This method terminates the robot launcher, resets the simulation state using
        the appropriate ROS or Gazebo services based on the visualization type,
        and relaunches the robot if a launcher is available.
        """

        for robot_launcher in self.robot_launchers:
            await robot_launcher.terminate()

        try:
            entities = []
            for robot_config in self.robot_configs:
                entities.append(robot_config["entity"])
            self.tools_launcher.reset(entities)
        except subprocess.TimeoutExpired as e:
            self.write_to_tool_terminal(f"{e}\n\n")
            raise Exception("Failed to reset simulator")

        robots_data = zip(self.robot_launchers, self.robot_configs)
        for launcher, cfg in robots_data:
            await launcher.run(cfg["entity"], cfg["start_pose"], cfg["extra_config"])

    async def start(self):
        """
        Start the RAM.

        RAM must be run in main thread to be able to handle signaling other processes,
        for instance ROS launcher.
        """
        self.consumer = await ManagerConsumer(self.host, self.port, self.process_message)
        LogManager.logger.info(
            f"Starting RAM consumer in {self.host}:{self.port}"
        )

        await self.consumer.start()

        async def signal_handler(sign, frame):
            LogManager.logger.info("Program exiting gracefully")
            self.running = False

            try:
                await self.consumer.stop()
            except Exception as e:
                LogManager.logger.exception("Exception stopping consumer")
            try:
                for process in self.application_processes:
                    stop_process_and_children(process)
                self.application_processes = []
            except Exception:
                LogManager.logger.exception("Exception stopping application process")

            if self.tools_launcher:
                try:
                    await self.tools_launcher.terminate()
                except Exception as e:
                    LogManager.logger.exception("Exception terminating tools launcher")

            try:
                for launcher in self.robot_launchers:
                    await launcher.terminate()
                self.robot_launchers = []
            except Exception as e:
                LogManager.logger.exception("Exception terminating robot launcher")

            if self.scene_launcher:
                try:
                    await self.scene_launcher.terminate()
                except Exception as e:
                    LogManager.logger.exception("Exception terminating scene launcher")
            exit()

        signal.signal(signal.SIGINT, signal_handler)

        while self.running:
            await asyncio.sleep(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "host", type=str, help="Host to listen to (0.0.0.0 or all hosts)"
    )
    parser.add_argument("port", type=int, help="Port to listen to")
    args = parser.parse_args()

    RAM = Manager(args.host, 7165)
    asyncio.run(RAM.start())
