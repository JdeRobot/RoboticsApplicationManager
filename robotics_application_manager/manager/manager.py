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

from queue import Queue
from uuid import uuid4
from transitions import Machine
from robotics_application_manager.comms import (
    ManagerConsumerMessageException,
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
    LauncherWorld,
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
            "trigger": "terminate_universe",
            "source": "world_ready",
            "dest": "connected",
            "before": "on_terminate_universe",
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
        # Code analysis
        {
            "trigger": "code_analysis",
            "source": [
                "idle",
                "connected",
                "paused",
                "world_ready",
                "tools_ready",
            ],
            "dest": "=",
            "before": "on_code_analysis",
        },
        # Code analysis
        {
            "trigger": "code_format",
            "source": [
                "idle",
                "connected",
                "paused",
                "world_ready",
                "tools_ready",
            ],
            "dest": "=",
            "before": "on_code_format",
        },
        # Code analysis
        {
            "trigger": "code_autocomplete",
            "source": [
                "idle",
                "connected",
                "paused",
                "world_ready",
                "tools_ready",
            ],
            "dest": "=",
            "before": "on_code_autocomplete",
        },
        # Theme change
        {
            "trigger": "change_style",
            "source": [
                "idle",
                "connected",
                "paused",
                "world_ready",
                "tools_ready",
                "application_running",
            ],
            "dest": "=",
            "before": "on_change_style",
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
        self.machine = Machine(
            model=self,
            states=Manager.states,
            transitions=Manager.transitions,
            initial="idle",
            send_event=True,
            after_state_change=self.state_change,
        )
        self.ros_version = subprocess.check_output(["bash", "-c", "echo $ROS_DISTRO"])
        self.queue = Queue()
        self.consumer = ManagerConsumer(host, port, self.queue)
        self.world_launcher = None
        self.world_type = None
        self.robot_launcher = None
        self.robot_config = None
        self.tools_launcher = None
        self.application_process = None
        self.running = True
        self.linter = Lint()

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

    def state_change(self, event):
        """
        Handle actions to be performed after a state change in the state machine.

        Parameters:
            event: The event object associated with the state change.
        """
        LogManager.logger.info(f"State changed to {self.state}")
        if self.consumer is not None:
            self.consumer.send_message({"state": self.state}, command="state-changed")

    def update(self, data):
        """
        Send an update message to the client with the provided data.

        Parameters:
            data: The data to be sent in the update message.
        """
        LogManager.logger.debug("Sending update to client")
        if self.consumer is not None:
            self.consumer.send_message({"update": data}, command="update")

    def update_bt_studio(self, data):
        """
        Send an update message to the client for BT Studio with the provided data.

        Parameters:
            data: The data to be sent in the update message.
        """
        LogManager.logger.debug("Sending update to client")
        if self.consumer is not None:
            self.consumer.send_message({"update": data}, command="update")

    def on_connect(self, event):
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
        self.consumer.send_message(
            {
                "robotics_backend_version": subprocess.check_output(
                    ["bash", "-c", "echo $IMAGE_TAG"]
                ),
                "ros_version": self.ros_version,
                "gpu_avaliable": check_gpu_acceleration(),
            },
            command="introspection",
        )

    def on_launch_world(self, event):
        """
        Handle the 'launch' event, transitioning the application from 'connected' to 'ready' state.

        This method initializes the launch process based on the provided configuration.

        During the launch process, it validates and processes the configuration data received from the event.
        It then creates and starts a LauncherWorld instance with the validated configuration.
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
        world_cfg = cfg_dict["world"]
        robot_cfg = cfg_dict["robot"]

        # Launch world
        try:
            if world_cfg["type"] == None:
                self.world_launcher = None
                LogManager.logger.info("Launch transition finished")
                return
            cfg = ConfigurationManager.validate(world_cfg)
            if "zip" in world_cfg:
                LogManager.logger.info("Launching universe from received zip")
                self.prepare_custom_universe(world_cfg)
            else:
                LogManager.logger.info("Launching world from the RB")

            LogManager.logger.info(cfg)
        except ValueError as e:
            LogManager.logger.error(f"Configuration validation failed: {e}")

        self.world_type = world_cfg["type"]

        self.world_launcher = LauncherWorld(**cfg.model_dump())
        LogManager.logger.info(str(self.world_launcher))

        # Launch robot
        self.robot_launcher = None
        if robot_cfg["type"] is not None:
            try:
                cfg = ConfigurationManager.validate(robot_cfg)
                LogManager.logger.info("Launching robot from the RB")
                LogManager.logger.info(cfg)
            except ValueError as e:
                LogManager.logger.error(f"Configuration validation failed: {e}")

            self.robot_launcher = LauncherRobot(**cfg.model_dump())
            self.robot_config = robot_cfg
            LogManager.logger.info(str(self.robot_launcher))

        self.world_launcher.run()
        if self.robot_launcher is not None:
            self.robot_launcher.run(
                robot_cfg["entity"], robot_cfg["start_pose"], robot_cfg["extra_config"]
            )
        LogManager.logger.info("Launch transition finished")

    def prepare_custom_universe(self, cfg_dict):
        """
        Prepare and extract a custom universe from a base64-encoded zip file.

        Then build it in the workspace.

        Parameters:
            cfg_dict (dict): Config dictionary containing the universe name and zip data
        """
        # Unzip the app
        if cfg_dict["zip"].startswith("data:"):
            _, _, zip_file = cfg_dict["zip"].partition("base64,")
        else:
            zip_file = cfg_dict["zip"]

        universe_ref = "/workspace/worlds/src/" + cfg_dict["name"]
        # Remove old content
        if os.path.exists("/workspace/worlds"):
            shutil.rmtree("/workspace/worlds", ignore_errors=False)

        # Create the folder if it doesn't exist
        universe_folder = universe_ref + "/"
        if not os.path.exists(universe_folder):
            os.makedirs(universe_folder)

        zip_destination = universe_ref + ".zip"
        with open(zip_destination, "wb") as result:
            result.write(base64.b64decode(zip_file))

        zip_ref = zipfile.ZipFile(zip_destination, "r")
        zip_ref.extractall(universe_folder + "/")
        zip_ref.close()

        os.system(
            '/bin/bash -c "cd /workspace/worlds; source /opt/ros/humble/setup.bash; colcon build --symlink-install; source install/setup.bash; cd ../.."'
        )

    def on_prepare_tools(self, event):

        LogManager.logger.info("Tools transition started")

        cfg_dict = event.kwargs.get("data", {})
        tools = cfg_dict["tools"]
        config = cfg_dict["config"]

        self.tools_launcher = LauncherTools(
            world_type=self.world_type, tools=tools, tools_config=config
        )

        self.tools_launcher.run(self.consumer)
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

    def on_style_check_application(self, event):
        """
        Handle the 'style_check' event.

        Does not change the state and returns the current state.

        It uses the linter to check if the style of the code is correct, if there
        are errors it writes them in all the consoles and raises the errors.

        Parameters:
            event (Event): Has the fields code (user code), exercise_id and type (bt-studio or robotics-academy) .

        Raises:
            Exception: with the errors found in the linter
        """
        # TODO: redo

        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        try:
            if app_cfg["type"] == "bt-studio":
                return
        except Exception:
            pass

        exercise_id = app_cfg["exercise_id"]
        code = app_cfg["code"]

        # Make code backwards compatible
        code = code.replace("from GUI import GUI", "import GUI")
        code = code.replace("from HAL import HAL", "import HAL")

        # Create executable app
        errors = self.linter.evaluate_code(
            code,
            exercise_id,
            self.ros_version,
            py_lint_source="pylint_checker_style.py",
        )

        if errors == "":
            errors = "No errors found"

        self.write_to_tool_terminal(errors + "\n\n")
        raise Exception(errors)

    def on_code_analysis(self, event):
        """
        Handle the 'code_analysis' event.

        Does not change the state and returns the current state.
        It uses pylint to check for the errors and warnings in the code.

        Parameters:
            event (Event): Has the fields code (user code) and disable_errors (disable errors id for pylint) .

        Returns:
            Sends the output of the pylint command in the code-analysis event for the frontend.
        """
        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        code_string = app_cfg["code"]
        disable_error_ids = app_cfg["disable_errors"]

        # if code string is empty
        if not code_string:
            LogManager.logger.info("User code not found")
            return

        # Save the code string to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
            temp_file.write(code_string.encode("utf-8"))
            temp_file_path = temp_file.name

        # terminal command
        command = [
            "pylint",
            "--output-format=json",
        ] + [temp_file_path]
        # '--extension-pkg-whitelist=cv2'

        # Add the disable option for specific error IDs
        if disable_error_ids:
            disable_str = ",".join(disable_error_ids)
            command.append(f"--disable={disable_str}")

        # run the command
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Decode the results
        pylint_output = result.stdout.decode("utf-8")
        pylint_errors = result.stderr.decode("utf-8")

        # Parse the JSON output if pylint output is not empty
        try:
            pylint_json = json.loads(pylint_output) if pylint_output else []
        except json.JSONDecodeError as e:
            LogManager.logger.info(f"Failed to parse JSON: {str(e)}")

        # Clean up the temporary file after Pylint run
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        if pylint_errors:
            LogManager.logger.info("Found errors in code")

        self.consumer.send_message(
            {"pylint_output": pylint_json, "pylint_errors": pylint_errors},
            command="code-analysis",
        )

    def on_code_format(self, event):
        """
        Handle the 'code_format' event.

        Does not change the state and returns the current state.
        It uses the black formatter to format the user code.

        Parameters:
            event (Event): Has the fields code (user code).

        Returns:
            Sends the output of the black format in
                the code-format event for the frontend.
        """
        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        code = app_cfg["code"]

        # if code string is empty
        if not code:
            LogManager.logger.info("User code not found")
            return

        try:
            # Format the code with Black
            formatted_code = black.format_str(code, mode=black.Mode())
            self.consumer.send_message(
                {
                    "formatted_code": formatted_code,
                },
                command="code-format",
            )
        except Exception as e:
            LogManager.logger.info("Error formating code" + str(e))

    def on_code_autocomplete(self, event):
        """
        Handle the 'code_autocomplete' event.

        Does not change the state and returns the current state.
        It uses jedi to find the possible autocompletions in the user code
            given the cursor position.

        Parameters:
            event (Event): Has the fields code (user code), line and col .

        Returns:
            Sends the possible completions in
                the code-autocomplete event for the frontend.
        """
        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        code = app_cfg["code"]
        line = app_cfg["line"]
        col = app_cfg["col"]

        jedi.settings.add_bracket_after_function = True

        # if code string is empty
        if not code:
            LogManager.logger.info("User code not found")
            return

        if not line or not col:
            LogManager.logger.info("User code position not found")
            return

        script = jedi.Script(code, path="/workspace/code/academy.py")

        try:
            completions = script.complete(line, col)
            serialized_completions = serialize_completions(completions)

            self.consumer.send_message(
                {
                    "completions": serialized_completions,
                },
                command="code-autocomplete",
            )
        except Exception as e:
            LogManager.logger.info("Error formating code" + str(e))

    def on_change_style(self, event):
        """
        Handle the 'change_style' event.

        This method changes the GTK theme and xterm colors without restarting.

        Parameters:
            event (Event): Has the field 'theme' (dark or light) in data.
        """
        app_cfg = event.kwargs.get("data", {})
        theme = app_cfg.get("theme", "dark")
        LogManager.logger.info(f"Changing style to {theme}")

        if theme == "dark":
            # Xterm dark theme: background black, foreground white
            xterm_cmd = "\033]11;black\007\033]10;white\007"
            gtk_theme = "Adwaita-dark"
        else:
            # Xterm light theme: background white, foreground black
            xterm_cmd = "\033]11;white\007\033]10;black\007"
            gtk_theme = "Adwaita"

        # Apply xterm theme to all active pseudoterminals
        try:
            self.write_to_tool_terminal(xterm_cmd)
        except Exception as e:
            LogManager.logger.exception(f"Error changing xterm style: {e}")

        # Update GTK settings for new windows
        # Write ~/.gtkrc-2.0
        gtkrc_path = os.path.expanduser("~/.gtkrc-2.0")
        try:
            with open(gtkrc_path, "w") as f:
                f.write(f'gtk-theme-name="{gtk_theme}"\n')
        except Exception as e:
            LogManager.logger.exception(f"Error writing {gtkrc_path}: {e}")

        # Write ~/.config/gtk-3.0/settings.ini
        gtk3_dir = os.path.expanduser("~/.config/gtk-3.0")
        gtk3_path = os.path.join(gtk3_dir, "settings.ini")
        try:
            os.makedirs(gtk3_dir, exist_ok=True)
            with open(gtk3_path, "w") as f:
                f.write("[Settings]\n")
                f.write(f"gtk-theme-name={gtk_theme}\n")
        except Exception as e:
            LogManager.logger.exception(f"Error writing {gtk3_path}: {e}")

        # Send a signal to force GTK applications to reload their theme
        try:
            # Also write to lxsession config which is what LXDE actually uses
            lxde_conf_dir = os.path.expanduser("~/.config/lxsession/LXDE")
            lxde_conf_path = os.path.join(lxde_conf_dir, "desktop.conf")
            os.makedirs(lxde_conf_dir, exist_ok=True)

            # Read existing or create new
            conf_lines = []
            if os.path.exists(lxde_conf_path):
                with open(lxde_conf_path, "r") as f:
                    conf_lines = f.readlines()

            # Ensure GTK section exists and update theme name
            gtk_section_found = False
            for i, line in enumerate(conf_lines):
                if line.strip() == "[GTK]":
                    gtk_section_found = True
                elif gtk_section_found and line.startswith("sNet/ThemeName="):
                    conf_lines[i] = f"sNet/ThemeName={gtk_theme}\\n"
                    break
            else:
                if not gtk_section_found:
                    conf_lines.append("[GTK]\\n")
                conf_lines.append(f"sNet/ThemeName={gtk_theme}\\n")

            with open(lxde_conf_path, "w") as f:
                f.writelines(conf_lines)

            # Reload window manager (Openbox) and LXPanel
            subprocess.run(
                [
                    "bash",
                    "-c",
                    "export DISPLAY=:1; lxpanelctl restart; openbox --reconfigure",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            LogManager.logger.exception(f"Error refreshing GTK applications: {e}")

    def on_run_application(self, event):
        """
        Handle the 'run_application' event.

        This method manages the process of running the user application,
        including preparing the code, handling console output,
        and launching the application process.

        Parameters:
            event: The event object containing application configuration and code data.
        """
        # Kill already running code
        try:
            proc = psutil.Process(self.application_process.pid)
            proc.suspend()
            proc.kill()
        except Exception:
            pass

        # Delete old files
        if os.path.exists("/workspace/code"):
            shutil.rmtree("/workspace/code", ignore_errors=False)
        os.mkdir("/workspace/code")

        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        entrypoint = app_cfg["entrypoint"]
        to_lint = app_cfg["linter"]

        # Unzip the app
        if app_cfg["code"].startswith("data:"):
            _, _, code = app_cfg["code"].partition("base64,")
        with open("/workspace/code/app.zip", "wb") as result:
            result.write(base64.b64decode(code))
        zip_ref = zipfile.ZipFile("/workspace/code/app.zip", "r")
        zip_ref.extractall("/workspace/code")
        zip_ref.close()

        if not os.path.isfile(entrypoint):
            LogManager.logger.info("User code not found")
            raise Exception("User code not found")

        _, file_extension = os.path.splitext(entrypoint)

        if file_extension == ".cpp" or entrypoint.endswith(".launch.py"):
            fds = os.listdir("/dev/pts/")
            console_fd = str(max(map(int, fds[:-1])))

            compile_process = subprocess.Popen(
                [
                    "cd /workspace/code && source /opt/ros/humble/setup.bash && colcon build && source install/setup.bash && cd ../.."
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
                raise Exception("Failed to compile")

            self.unpause_sim()
            if entrypoint.endswith(".launch.py"):
                self.application_process = subprocess.Popen(
                    [
                        f"source /workspace/code/install/setup.bash && ros2 launch {entrypoint}"
                    ],
                    stdin=open("/dev/pts/" + console_fd, "r"),
                    stdout=open("/dev/pts/" + console_fd, "w"),
                    stderr=sys.stdout,
                    bufsize=1024,
                    universal_newlines=True,
                    shell=True,
                    executable="/bin/bash",
                    start_new_session=True,
                )
            else:

                self.application_process = subprocess.Popen(
                    [
                        "source /workspace/code/install/setup.bash && ros2 run academy academyCode"
                    ],
                    stdin=open("/dev/pts/" + console_fd, "r"),
                    stdout=open("/dev/pts/" + console_fd, "w"),
                    stderr=sys.stdout,
                    bufsize=1024,
                    universal_newlines=True,
                    shell=True,
                    executable="/bin/bash",
                    start_new_session=True,
                )
            return

        # Pass the linter
        errors = self.linter.evaluate_source_code(to_lint)
        failed_linter = False

        for error in errors:
            if error != "":
                failed_linter = True
                self.write_to_tool_terminal(error + "\n\n")

        if failed_linter:
            raise Exception(errors)

        fds = os.listdir("/dev/pts/")
        console_fd = str(max(map(int, fds[:-1])))

        self.unpause_sim()
        self.application_process = subprocess.Popen(
            ["python3", entrypoint],
            stdin=open("/dev/pts/" + console_fd, "r"),
            stdout=open("/dev/pts/" + console_fd, "w"),
            stderr=sys.stdout,
            bufsize=1024,
            universal_newlines=True,
        )

        LogManager.logger.info("Run application transition finished")

    def on_terminate_application(self, event):
        """
        Handle the 'terminate_application' event.

        Terminates the currently running application process,
        pauses and resets the simulation if applicable.

        Parameters:
            event: The event object associated with the termination request.
        """
        if self.application_process:
            try:
                stop_process_and_children(self.application_process)
                self.application_process = None
                self.pause_sim()
                self.reset_sim()
            except Exception:
                LogManager.logger.exception("No application running")
                print(traceback.format_exc())

    def on_terminate_tools(self, event):

        self.tools_launcher.terminate()
        self.tools_launcher = None

    def on_terminate_universe(self, event):
        """
        Handle the 'terminate_universe' event.

        Terminates the world and robot launchers if they exist
        and terminates related Harmonic processes.

        Parameters:
            event: The event object associated with the termination request.
        """
        if self.world_launcher is not None:
            self.world_launcher.terminate()
            self.world_launcher = None
            self.world_type = None
        if self.robot_launcher is not None:
            self.robot_launcher.terminate()
            self.robot_launcher = None

    def on_disconnect(self, event):
        """
        Handle the 'disconnect' event.

        This method stops all running processes,
        terminates launchers, and restarts the script.
        """

        if self.application_process:
            try:
                stop_process_and_children(self.application_process)
                self.application_process = None
            except Exception as e:
                LogManager.logger.exception("Exception stopping application process")

        if self.tools_launcher:
            try:
                self.tools_launcher.terminate()
            except Exception as e:
                LogManager.logger.exception("Exception terminating tools launcher")

        if self.robot_launcher:
            try:
                self.robot_launcher.terminate()
            except Exception as e:
                LogManager.logger.exception("Exception terminating robot launcher")

        if self.world_launcher:
            try:
                self.world_launcher.terminate()
            except Exception as e:
                LogManager.logger.exception("Exception terminating world launcher")

    def process_message(self, message):
        if message.command == "gui":
            if self.tools_launcher is not None:
                self.tools_launcher.pass_msg(message.data)
            return

        self.trigger(message.command, data=message.data or None)
        response = {"message": f"Exercise state changed to {self.state}"}
        self.consumer.send_message(message.response(response))

    def on_pause(self, msg):
        if self.application_process is not None:
            proc = psutil.Process(self.application_process.pid)
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
            self.reset_sim()

    def on_resume(self, msg):
        """
        Resume the application process if it exists, otherwise reset the simulation.

        Parameters:
            msg: The event or message triggering the resume action.
        """
        if self.application_process is not None:
            proc = psutil.Process(self.application_process.pid)
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
            self.reset_sim()

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

    def reset_sim(self):
        """
        Reset the simulation environment and relaunch the robot if applicable.

        This method terminates the robot launcher, resets the simulation state using
        the appropriate ROS or Gazebo services based on the visualization type,
        and relaunches the robot if a launcher is available.
        """
        if self.robot_launcher:
            self.robot_launcher.terminate()

        try:
            entity = None
            if self.robot_config is not None:
                entity = self.robot_config["entity"]
            self.tools_launcher.reset(entity)
        except subprocess.TimeoutExpired as e:
            self.write_to_tool_terminal(f"{e}\n\n")
            raise Exception("Failed to reset simulator")

        if self.robot_launcher:
            try:
                self.robot_launcher.run(
                    self.robot_config["entity"],
                    self.robot_config["start_pose"],
                    self.robot_config["extra_config"],
                )
            except Exception as e:
                LogManager.logger.exception("Exception terminating world launcher")

    def start(self):
        """
        Start the RAM.

        RAM must be run in main thread to be able to handle signaling other processes,
        for instance ROS launcher.
        """
        LogManager.logger.info(
            f"Starting RAM consumer in {self.consumer.server}:{self.consumer.port}"
        )

        self.consumer.start()

        def signal_handler(sign, frame):
            print("\nprogram exiting gracefully")
            self.running = False

            try:
                self.consumer.stop()
            except Exception as e:
                LogManager.logger.exception("Exception stopping consumer")

            if self.application_process:
                try:
                    stop_process_and_children(self.application_process)
                    self.application_process = None
                except Exception as e:
                    LogManager.logger.exception(
                        "Exception stopping application process"
                    )

            if self.tools_launcher:
                try:
                    self.tools_launcher.terminate()
                except Exception as e:
                    LogManager.logger.exception("Exception terminating tools launcher")

            if self.robot_launcher:
                try:
                    self.robot_launcher.terminate()
                except Exception as e:
                    LogManager.logger.exception("Exception terminating robot launcher")

            if self.world_launcher:
                try:
                    self.world_launcher.terminate()
                except Exception as e:
                    LogManager.logger.exception("Exception terminating world launcher")

            exit()

        signal.signal(signal.SIGINT, signal_handler)

        while self.running:
            message = None
            try:
                if self.queue.empty():
                    time.sleep(0.1)
                else:
                    message = self.queue.get()
                    self.process_message(message)
            except Exception as e:
                if message is not None:
                    ex = ManagerConsumerMessageException(id=message.id, message=str(e))
                else:
                    ex = ManagerConsumerMessageException(
                        id=str(uuid4()), message=str(e)
                    )
                self.consumer.send_message(ex)
                LogManager.logger.error(e, exc_info=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "host", type=str, help="Host to listen to  (0.0.0.0 or all hosts)"
    )
    parser.add_argument("port", type=int, help="Port to listen to")
    args = parser.parse_args()

    RAM = Manager(args.host, args.port)
    RAM.start()
