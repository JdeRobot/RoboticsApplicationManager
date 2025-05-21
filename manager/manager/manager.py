from __future__ import annotations
import json
import sys
import tempfile

import black



sys.path.insert(0, '/RoboticsApplicationManager')

import os
import signal
import subprocess
import sys
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

from manager.comms.consumer_message import ManagerConsumerMessageException
from manager.comms.new_consumer import ManagerConsumer
from manager.libs.process_utils import check_gpu_acceleration, get_class_from_file
from manager.libs.launch_world_model import ConfigurationManager
from manager.manager.launcher.launcher_world import LauncherWorld
from manager.manager.launcher.launcher_robot import LauncherRobot
from manager.manager.launcher.launcher_visualization import LauncherVisualization
from manager.ram_logging.log_manager import LogManager
from manager.libs.applications.compatibility.server import Server
from manager.libs.applications.compatibility.file_watchdog import FileWatchdog
from manager.manager.application.robotics_python_application_interface import (
    IRoboticsPythonApplication,
)
from manager.libs.process_utils import stop_process_and_children
from manager.manager.lint.linter import Lint
from manager.manager.editor.serializers import serialize_completions

class Manager:
    states = [
        "idle",
        "connected",
        "world_ready",
        "visualization_ready",
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
            "trigger": "prepare_visualization",
            "source": "world_ready",
            "dest": "visualization_ready",
            "before": "on_prepare_visualization",
        },
        # Transitions for state visualization_ready
        {
            "trigger": "run_application",
            "source": ["visualization_ready", "paused", "application_running"],
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
            "source": ["visualization_ready", "application_running", "paused"],
            "dest": "visualization_ready",
            "before": "on_terminate_application",
        },
        {
            "trigger": "terminate_visualization",
            "source": "visualization_ready",
            "dest": "world_ready",
            "before": "on_terminate_visualization",
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
            "source": ["idle", "connected", "paused", "world_ready","visualization_ready"],
            "dest": "=",
            "before": "on_style_check_application",
        },
        # Code analysis 
        {
            "trigger": "code_analysis",
            "source": ["idle", "connected", "paused", "world_ready","visualization_ready"],
            "dest": "=",
            "before": "on_code_analysis",
        },
        # Code analysis 
        {
            "trigger": "code_format",
            "source": ["idle", "connected", "paused", "world_ready","visualization_ready"],
            "dest": "=",
            "before": "on_code_format",
        },
        # Code analysis 
        {
            "trigger": "code_autocomplete",
            "source": ["idle", "connected", "paused", "world_ready","visualization_ready"],
            "dest": "=",
            "before": "on_code_autocomplete",
        }
    ]

    def __init__(self, host: str, port: int):

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
        self.robot_launcher = None
        self.visualization_launcher = None
        self.visualization_type = None
        self.application_process = None
        self.running = True
        self.gui_server = None
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
        LogManager.logger.info(f"State changed to {self.state}")
        if self.consumer is not None:
            self.consumer.send_message({"state": self.state}, command="state-changed")

    def update(self, data):
        LogManager.logger.debug(f"Sending update to client")
        if self.consumer is not None:
            self.consumer.send_message({"update": data}, command="update")

    def update_bt_studio(self, data):
        LogManager.logger.debug(f"Sending update to client")
        if self.consumer is not None:
            self.consumer.send_message({"update": data}, command="update")

    def on_connect(self, event):
        """
        This method is triggered when the application transitions to the 'connected' state.
        It sends an introspection message to a consumer with key information.

        Parameters:
            event (Event): The event object containing data related to the 'connect' event.

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
        Handles the 'launch' event, transitioning the application from 'connected' to 'ready' state.
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
        world_cfg = cfg_dict['world']
        robot_cfg = cfg_dict['robot']

        # Launch world
        try:
            if world_cfg['world'] == None:
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

        self.world_launcher = LauncherWorld(**cfg.model_dump())
        LogManager.logger.info(str(self.world_launcher))
        self.world_launcher.run()
        LogManager.logger.info("Launch transition finished")

        # Launch robot
        try:
            if robot_cfg['world'] == None:
                self.robot_launcher = None
                LogManager.logger.info("Launch transition finished")
                return
            cfg = ConfigurationManager.validate(robot_cfg)
            LogManager.logger.info("Launching robot from the RB")

            LogManager.logger.info(cfg)
        except ValueError as e:
            LogManager.logger.error(f"Configuration validation failed: {e}")

        self.robot_launcher = LauncherRobot(**cfg.model_dump())
        LogManager.logger.info(str(self.robot_launcher))
        self.robot_launcher.run(robot_cfg['start_pose'])
        LogManager.logger.info("Launch transition finished")

    def prepare_custom_universe(self, cfg_dict):

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

        os.system('/bin/bash -c "cd /workspace/worlds; source /opt/ros/humble/setup.bash; colcon build --symlink-install; source install/setup.bash; cd ../.."')

    def on_prepare_visualization(self, event):

        LogManager.logger.info("Visualization transition started")

        cfg_dict = event.kwargs.get("data", {})
        self.visualization_type = cfg_dict['type']
        config_file = cfg_dict['file']

        self.visualization_launcher = LauncherVisualization(
            visualization=self.visualization_type,
            visualization_config_path = config_file
        )
        
        self.visualization_launcher.run()

        if self.visualization_type in ["gazebo_rae", "gzsim_rae", "console"]:
            self.gui_server = Server(2303, self.update)
            self.gui_server.start()
        elif self.visualization_type in ["bt_studio", "bt_studio_gz"]:
            self.gui_server = FileWatchdog('/tmp/tree_state', self.update_bt_studio)
            self.gui_server.start()

        LogManager.logger.info("Visualization transition finished")

    def add_frequency_control(self, code):
        frequency_control_code_imports = """
import time
from datetime import datetime
ideal_cycle = 20
"""
        code = frequency_control_code_imports + code
        infinite_loop = re.search(
            r"[^ ]while\s*\(\s*True\s*\)\s*:|[^ ]while\s*True\s*:|[^ ]while\s*1\s*:|[^ ]while\s*\(\s*1\s*\)\s*:",
            code,
        )
        frequency_control_code_pre = """
    start_time_internal_freq_control = datetime.now()
            """
        code = (
            code[: infinite_loop.end()]
            + frequency_control_code_pre
            + code[infinite_loop.end() :]
        )
        frequency_control_code_post = """
    finish_time_internal_freq_control = datetime.now()
    dt = finish_time_internal_freq_control - start_time_internal_freq_control
    ms = (dt.days * 24 * 60 * 60 + dt.seconds) * 1000 + dt.microseconds / 1000.0

    if (ms < ideal_cycle):
        time.sleep((ideal_cycle - ms) / 1000.0)
"""
        code = code + frequency_control_code_post
        return code

    def on_style_check_application(self, event):
        """
        Handles the 'style_check' event, does not change the state and returns the current state.

        It uses the linter to check if the style of the code is correct, if there 
        are errors it writes them in all the consoles and raises the errors.

        Parameters:
            event (Event): Has the fields code (user code), exercise_id and type (bt-studio or robotics-academy) .

        Raises:
            Exception: with the errors found in the linter
        """
        def find_docker_console():
            """Search console in docker different of /dev/pts/0"""
            pts_consoles = [f"/dev/pts/{dev}" for dev in os.listdir('/dev/pts/') if dev.isdigit()]
            consoles = []
            for console in pts_consoles:
                if console != "/dev/pts/0":
                    try:
                        # Search if it's a console
                        with open(console, 'w') as f:
                            f.write("")
                        consoles.append(console)
                    except Exception:
                        # Continue searching
                        continue
            
            # raise Exception("No active console other than /dev/pts/0")
            return consoles

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
        errors = self.linter.evaluate_code(code, exercise_id, self.ros_version, py_lint_source="pylint_checker_style.py")

        if errors == "":
            errors = "No errors found"

        console_path = find_docker_console()
        for i in console_path:
            with open(i, 'w') as console:
                console.write(errors + "\n\n")

        raise Exception(errors)

    def on_code_analysis(self, event):    
        """
        Handles the 'code_analysis' event, does not change the state and returns the current state.

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
            temp_file.write(code_string.encode('utf-8'))
            temp_file_path = temp_file.name
            
        
        # terminal command
        command = ['pylint', '--output-format=json',] + [temp_file_path]
        # '--extension-pkg-whitelist=cv2'
        
        # Add the disable option for specific error IDs
        if disable_error_ids:
            disable_str = ','.join(disable_error_ids)
            command.append(f'--disable={disable_str}')
        
        # run the command
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Decode the results
        pylint_output = result.stdout.decode('utf-8')
        pylint_errors = result.stderr.decode('utf-8')
        
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
            {
                "pylint_output": pylint_json,
                "pylint_errors": pylint_errors
            },
            command="code-analysis",
        )

    def on_code_format(self, event):
        """
        Handles the 'code_format' event, does not change the state and returns the current state.

        It uses the black formatter to format the user code.

        Parameters:
            event (Event): Has the fields code (user code).

        Returns:
            Sends the output of the black format in the code-format event for the frontend.
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
            LogManager.logger.info('Error formating code' + str(e))

    def on_code_autocomplete(self, event):
        """
        Handles the 'code_autocomplete' event, does not change the state and returns the current state.

        It uses jedi to find the possible autocompletions in the user code give the cursor position.

        Parameters:
            event (Event): Has the fields code (user code), line and col .

        Returns:
            Sends the possible completions in the code-autocomplete event for the frontend.
        """

        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        code = app_cfg["code"]
        line = app_cfg["line"]
        col = app_cfg["col"]

        jedi.settings.add_bracket_after_function= True
        
        # if code string is empty
        if not code:
            LogManager.logger.info("User code not found")
            return
        
        if not line or not col:
            LogManager.logger.info("User code position not found")
            return
        
        script = jedi.Script(code, path='/workspace/code/academy.py')

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
            LogManager.logger.info('Error formating code' + str(e))
        
    def on_run_application(self, event):
        def find_docker_console():
            """Search console in docker different of /dev/pts/0"""
            pts_consoles = [f"/dev/pts/{dev}" for dev in os.listdir('/dev/pts/') if dev.isdigit()]
            consoles = []
            for console in pts_consoles:
                if console != "/dev/pts/0":
                    try:
                        # Search if it's a console
                        with open(console, 'w') as f:
                            f.write("")
                        consoles.append(console)
                    except Exception:
                        # Continue searching
                        continue
            
            # raise Exception("No active console other than /dev/pts/0")
            return consoles
        
        def prepare_RA_code(code_path):
            f = open(code_path, "r")
            code = f.read()
            f.close()

            # Make code backwards compatible
            code = code.replace("from GUI import GUI", "import GUI")
            code = code.replace("from HAL import HAL", "import HAL")

            # Create executable app
            errors = self.linter.evaluate_code(code, self.ros_version)
            if errors == "":

                code = self.add_frequency_control(code)
                f = open(code_path, "w")
                f.write(code)
                f.close()

            else:
                console_path = find_docker_console()
                for i in console_path:
                    with open(i, 'w') as console:
                        console.write(errors + "\n\n")

                raise Exception(errors)

        # Kill already running code
        try:
            proc = psutil.Process(self.application_process.pid)
            proc.suspend()
            proc.kill()
        except Exception:
            pass

        # Delete old files
        if os.path.exists("/workspace/code"):
            shutil.rmtree("/workspace/code")
        os.mkdir("/workspace/code")

        # Extract app config
        app_cfg = event.kwargs.get("data", {})
        type = app_cfg["type"]

        if type == "robotics-academy":
            code_path = "/workspace/code/academy.py"
        elif type == "bt-studio":
            code_path = "/workspace/code/execute_docker.py"

        # Unzip the app
        if app_cfg["code"].startswith("data:"):
            _, _, code = app_cfg["code"].partition("base64,")
        with open("/workspace/code/app.zip", "wb") as result:
            result.write(base64.b64decode(code))
        zip_ref = zipfile.ZipFile("/workspace/code/app.zip", "r")
        zip_ref.extractall("/workspace/code")
        zip_ref.close()

        if not os.path.isfile(code_path):
            LogManager.logger.info("User code not found")
            raise Exception("User code not found")
        
        try:
            if (type == "robotics-academy"):
                prepare_RA_code(code_path)

            fds = os.listdir("/dev/pts/")
            console_fd = str(max(map(int, fds[:-1])))

            self.application_process = subprocess.Popen(
                ["python3", code_path],
                stdin=open('/dev/pts/' + console_fd, 'r'),
                stdout=sys.stdout,
                stderr=subprocess.STDOUT,
                bufsize=1024,
                universal_newlines=True,
            )
            self.unpause_sim()
        except:
            LogManager.logger.info("Run application failed")
        
        LogManager.logger.info("Run application transition finished")
    
    def terminate_harmonic_processes(self):
        """
        Terminate all processes within the Docker container whose command line contains 'gz' or 'launch'.
        """
        LogManager.logger.info("Terminate Harmonic process")
        keywords = ['gz', 'launch']
        for keyword in keywords:
            try:
                ps_aux_cmd = ['ps', 'aux']
                grep_cmd = ['grep', keyword]
                grep_exclude_cmd = ['grep', '-v', 'grep']

                ps_aux_proc = subprocess.Popen(ps_aux_cmd, stdout=subprocess.PIPE)
                grep_proc = subprocess.Popen(grep_cmd, stdin=ps_aux_proc.stdout, stdout=subprocess.PIPE)
                exclude_grep_proc = subprocess.Popen(grep_exclude_cmd, stdin=grep_proc.stdout, stdout=subprocess.PIPE)

                ps_aux_proc.stdout.close()
                grep_proc.stdout.close()

                output = exclude_grep_proc.communicate()[0].decode('utf-8')
                
                for line in output.splitlines():
                    try:
                        # Extract PID
                        pid = int(line.split()[1])
                        subprocess.run(['kill', '-15', str(pid)], check=True)
                        
                        # Avoid zombies
                        try:
                            os.waitpid(pid, 0)
                        except ChildProcessError:
                            pass
                    except Exception as e:
                        LogManager.logger.exception(f"Failed to terminate process with line: {line}. Error: {e}")

            except Exception as e:
                LogManager.logger.exception(
                    f"Failed to search and terminate processes with keyword '{keyword}': {e}"
                )

    def on_terminate_application(self, event):

        if self.application_process:
            try:
                stop_process_and_children(self.application_process)
                self.application_process = None
                self.pause_sim()
                self.reset_sim()
            except Exception:
                LogManager.logger.exception("No application running")
                print(traceback.format_exc())
        self.terminate_harmonic_processes()

    def on_terminate_visualization(self, event):

        self.visualization_launcher.terminate()
        if self.gui_server != None:
            self.gui_server.stop()
            self.gui_server = None
        self.terminate_harmonic_processes()

    def on_terminate_universe(self, event):

        if self.world_launcher != None:
            self.world_launcher.terminate()
        if self.robot_launcher != None:
            self.robot_launcher.terminate()
        self.terminate_harmonic_processes()

    def on_disconnect(self, event):

        try:
            self.consumer.stop()
        except Exception as e:
            LogManager.logger.exception("Exception stopping consumer")

        if self.application_process:
            try:
                stop_process_and_children(self.application_process)
                self.application_process = None
            except Exception as e:
                LogManager.logger.exception("Exception stopping application process")

        if self.visualization_launcher:
            try:
                self.visualization_launcher.terminate()
            except Exception as e:
                LogManager.logger.exception(
                    "Exception terminating visualization launcher"
                )

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
        
        self.terminate_harmonic_processes()

        # Reiniciar el script
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def process_message(self, message):
        if message.command == "gui":
            self.gui_server.send(message.data)
            return

        self.trigger(message.command, data=message.data or None)
        response = {"message": f"Exercise state changed to {self.state}"}
        self.consumer.send_message(message.response(response))

    def on_pause(self, msg):
        if self.application_process is not None:
            try:
                proc = psutil.Process(self.application_process.pid)
                proc.suspend()
                self.pause_sim()
            except Exception as e:
                LogManager.logger.exception("Error suspending process")
        else:
            LogManager.logger.warning("Application process was None during pause. Calling termination.")
            self.on_terminate_application(msg)

    def on_resume(self, msg):
        if self.application_process is not None:
            try:
                proc = psutil.Process(self.application_process.pid)
                proc.resume()
                self.unpause_sim()
            except Exception as e:
                LogManager.logger.exception("Error suspending process")
        else:
            LogManager.logger.warning("Application process was None during resume. Calling termination.")
            self.on_terminate_application(msg) 

    def pause_sim(self):
        if self.visualization_type in ["gzsim_rae", "bt_studio_gz"]:
            self.call_gzservice("$(gz service -l | grep '^/world/\w*/control$')","gz.msgs.WorldControl","gz.msgs.Boolean","3000","pause: true")
        elif not self.visualization_type in ["console"]:
            self.call_service("/pause_physics", "std_srvs/srv/Empty")

    def unpause_sim(self):
        if self.visualization_type in ["gzsim_rae", "bt_studio_gz"]:
            self.call_gzservice("$(gz service -l | grep '^/world/\w*/control$')","gz.msgs.WorldControl","gz.msgs.Boolean","3000","pause: false")
        elif not self.visualization_type in ["console"]:
            self.call_service("/unpause_physics", "std_srvs/srv/Empty")

    def reset_sim(self):
        if self.robot_launcher:
            self.robot_launcher.terminate()
            
        if self.visualization_type in ["gzsim_rae", "bt_studio_gz"]:
            if self.is_ros_service_available("/drone0/platform/state_machine/_reset"):
                self.call_service("/drone0/platform/state_machine/_reset", "std_srvs/srv/Trigger", "{}")
            self.call_gzservice("$(gz service -l | grep '^/world/\w*/control$')","gz.msgs.WorldControl","gz.msgs.Boolean","3000","reset: {all: true}")
            if self.is_ros_service_available("/drone0/controller/_reset"):
                self.call_service("/drone0/controller/_reset", "std_srvs/srv/Trigger", "{}")
        elif not self.visualization_type in ["console"]:
            self.call_service("/reset_world", "std_srvs/srv/Empty")

        if self.robot_launcher:
            try:
                self.robot_launcher.run()
            except Exception as e:
                LogManager.logger.exception("Exception terminating world launcher")

    def call_service(self, service, service_type, request_data="{}"):
        command = f"ros2 service call {service} {service_type} '{request_data}'"
        subprocess.call(
            f"{command}",
            shell=True,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            bufsize=1024,
            universal_newlines=True,
        )
    
    def call_gzservice(self, service, reqtype, reptype, timeout, req):
        command = f"gz service -s {service} --reqtype {reqtype} --reptype {reptype} --timeout {timeout} --req '{req}'"
        subprocess.call(
            f"{command}",
            shell=True,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            bufsize=1024,
            universal_newlines=True,
        )

    def is_ros_service_available(self, service_name):
        try:
            result = subprocess.run(['ros2', 'service', 'list', '--include-hidden-services'], capture_output=True, text=True, check=True)
            return service_name in result.stdout
        except subprocess.CalledProcessError as e:
            LogManager.logger.exception(f"Error checking service availability: {e}")
            return False
    
    def start(self):
        """
        Starts the RAM
        RAM must be run in main thread to be able to handle signaling other processes, for instance ROS launcher.
        """
        LogManager.logger.info(
            f"Starting RAM consumer in {self.consumer.server}:{self.consumer.port}"
        )

        self.consumer.start()

        def signal_handler(sign, frame):
            print("\nprogram exiting gracefully")
            self.running = False
            if self.gui_server is not None:
                try:
                    self.gui_server.stop()
                except Exception as e:
                    LogManager.logger.exception("Exception stopping GUI server")

            try:
                self.consumer.stop()
            except Exception as e:
                LogManager.logger.exception("Exception stopping consumer")

            if self.application_process:
                try:
                    stop_process_and_children(self.application_process)
                    self.application_process = None
                except Exception as e:
                    LogManager.logger.exception("Exception stopping application process")

            if self.visualization_launcher:
                try:
                    self.visualization_launcher.terminate()
                except Exception as e:
                    LogManager.logger.exception(
                        "Exception terminating visualization launcher"
                    )

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
            
            self.terminate_harmonic_processes()
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
