from __future__ import annotations

import base64
import os
import signal
import subprocess
import sys
import psutil
import time
import rosservice
import multiprocessing
import traceback
import zipfile
from queue import Queue
from uuid import uuid4


from transitions import Machine

from src.manager.comms.consumer_message import ManagerConsumerMessageException
from src.manager.comms.new_consumer import ManagerConsumer
from src.manager.libs.process_utils import check_gpu_acceleration, get_class_from_file
from src.manager.libs.launch_world_model import ConfigurationManager
from src.manager.manager.launcher.launcher_world import LauncherWorld
from src.manager.manager.launcher.launcher_visualization import LauncherVisualization
from src.manager.ram_logging.log_manager import LogManager
from src.manager.libs.applications.compatibility.server import Server
from src.manager.manager.application.robotics_python_application_interface import IRoboticsPythonApplication
from src.manager.libs.process_utils import stop_process_and_children


class Manager:
    states = [
        "idle",
        "connected",
        "world_ready",
        "visualization_ready",
        "application_running",
        "paused"
    ]

    transitions = [
        # Transitions for state idle
        {'trigger': 'connect', 'source': 'idle',
            'dest': 'connected', 'before': 'on_connect'},
        # Transitions for state connected
        {'trigger': 'launch_world', 'source': 'connected',
            'dest': 'world_ready', 'before': 'on_launch_world'},
        # Transitions for state world ready
        {'trigger': 'prepare_visualization',
            'source': 'world_ready', 'dest': 'visualization_ready', 'before': 'on_prepare_visualization'},
        # Transitions for state visualization_ready
        {'trigger': 'run_application', 'source': [
            'visualization_ready', 'paused'], 'dest': 'application_running',  'before': 'on_run_application'},
        # Transitions for state application_running
        {'trigger': 'pause', 'source': 'application_running',
            'dest': 'paused', 'before': 'on_pause'},
        {'trigger': 'terminate', 'source': ['ready', 'application_running', 'paused'],
            'dest': 'connected', 'before': 'on_terminate'},
        {'trigger': 'stop', 'source': [
            'application_running', 'paused'], 'dest': 'ready', 'before': 'on_stop'},
        # Global transitions
        {'trigger': 'disconnect', 'source': '*',
            'dest': 'idle', 'before': 'on_disconnect'},

    ]

    def __init__(self, host: str, port: int):
        self.__code_loaded = False
        self.machine = Machine(model=self, states=Manager.states, transitions=Manager.transitions,
                               initial='idle', send_event=True, after_state_change=self.state_change)

        self.queue = Queue()

        self.consumer = ManagerConsumer(host, port, self.queue)
        self.world_launcher = None
        self.visualization_launcher = None
        self.application = None
        self.application_process = None
        self.running = True
        self.gui_server = None

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
            self.consumer.send_message(
                {'state': self.state}, command="state-changed")

    def update(self, data):
        LogManager.logger.debug(f"Sending update to client")
        if self.consumer is not None:
            self.consumer.send_message({'update': data}, command="update")

    def on_connect(self, event):
        """
        This method is triggered when the application transitions to the 'connected' state.
        It sends an introspection message to a consumer with key information.

        Parameters:
            event (Event): The event object containing data related to the 'connect' event.

        The message sent to the consumer includes:
        - `radi_version`: The current RADI (Robotics Application Docker Image) version.
        - `ros_version`: The current ROS (Robot Operating System) distribution version.
        - `gpu_avaliable`: Boolean indicating whether GPU acceleration is available.
        """
        self.consumer.send_message({'radi_version': subprocess.check_output(['bash', '-c', 'echo $IMAGE_TAG']), 'ros_version': subprocess.check_output(
            ['bash', '-c', 'echo $ROS_DISTRO']), 'gpu_avaliable': check_gpu_acceleration(), }, command="introspection")

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

        try:
            config_dict = event.kwargs.get('data', {})
            configuration = ConfigurationManager.validate(config_dict)
        except ValueError as e:
            LogManager.logger.error(f'Configuration validotion failed: {e}')

        """ get_user_world(configuration.launch_file) """

        self.world_launcher = LauncherWorld(**configuration.model_dump())
        self.world_launcher.run()
        LogManager.logger.info("Launch transition finished")

    def on_prepare_visualization(self, event):
        LogManager.logger.info("Visualization transition started")

        visualization_type = event.kwargs.get('data', {})
        self.visualization_launcher = LauncherVisualization(
            visualization=visualization_type)
        self.visualization_launcher.run()

        if visualization_type == "gazebo_rae":
            self.gui_server = Server(2303, self.update)
            self.gui_server.start()
        LogManager.logger.info("Visualization transition finished")

    def on_run_application(self, event):
        application_configuration = event.kwargs.get('data', {})
        application_file = application_configuration['template']
        exercise_id = "autoparking_newmanager"
        
        application_module = os.path.expandvars(application_file)
        application_class = get_class_from_file(application_module, "Exercise")

        if self.application_process is not None:
            proc = psutil.Process(self.application_process.pid)
            proc.resume()
        else:
            try:
                f = open("/workspace/code/academy.py", "w")
                f.write(application_configuration["code"])
                f.close()   
                self.application_process = subprocess.Popen(['python3', '/RoboticsAcademy/test_app.py'], stdout=sys.stdout, stderr=subprocess.STDOUT,
                                    bufsize=1024, universal_newlines=True)            
                rosservice.call_service("/gazebo/unpause_physics", [])
            except Exception as e:
                # TODO return linter errors to the frontend
                print("Exception encountered: " + str(e))
     

    def on_stop(self, event):
        stop_process_and_children(self.application_process)
        self.application_process = None
        rosservice.call_service('/gazebo/pause_physics', [])
        rosservice.call_service("/gazebo/reset_world", [])
        self.__code_loaded = False


    def on_terminate(self, event):
        """Terminates the application and the launcher \
            and sets the variable __code_loaded to False"""
        try:
            stop_process_and_children(self.application_process)
            self.application_process = None
            self.__code_loaded = False
            self.launcher.terminate()
        except Exception:
            LogManager.logger.exception(f"Exception terminating instance")
            print(traceback.format_exc())

    def on_disconnect(self, event):
        try:
            self.consumer.stop()
            self.__code_loaded = False
            stop_process_and_children(self.application_process)
            self.application_process = None
            self.launcher.terminate()
        except Exception as e:
            LogManager.logger.exception(f"Exception terminating instance")
            print(traceback.format_exc())
        python = sys.executable
        os.execl(python, python, *sys.argv)


    def code_loaded(self, event):
        return self.__code_loaded

    def process_messsage(self, message):
        self.trigger(message.command, data=message.data or None)
        response = {"message": f"Exercise state changed to {self.state}"}
        self.consumer.send_message(message.response(response))

    def on_pause(self, msg):
        proc = psutil.Process(self.application_process.pid)
        proc.suspend()
        rosservice.call_service('/gazebo/pause_physics', [])
        self.__code_loaded = False

    def on_resume(self, msg):
        proc = psutil.Process(self.application_process.pid)
        proc.resume()
        rosservice.call_service("/gazebo/unpause_physics", [])

    def start(self):
        """
        Starts the RAM
        RAM must be run in main thread to be able to handle signaling other processes, for instance ROS launcher.
        """
        LogManager.logger.info(
            f"Starting RAM consumer in {self.consumer.server}:{self.consumer.port}")

        self.consumer.start()

        def signal_handler(sign, frame):
            print("\nprogram exiting gracefully")
            self.running = False
            stop_process_and_children(self.application_process)
            self.application_process = None
            self.__code_loaded = False
            self.launcher.terminate()

        signal.signal(signal.SIGINT, signal_handler)

        while self.running:
            message = None
            try:
                if self.queue.empty():
                    time.sleep(0.1)
                else:
                    message = self.queue.get()
                    self.process_messsage(message)
            except Exception as e:
                if message is not None:
                    ex = ManagerConsumerMessageException(
                        id=message.id, message=str(e))
                else:
                    ex = ManagerConsumerMessageException(
                        id=str(uuid4()), message=str(e))
                self.consumer.send_message(ex)
                LogManager.logger.error(e, exc_info=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "host", type=str, help="Host to listen to  (0.0.0.0 or all hosts)")
    parser.add_argument("port", type=int, help="Port to listen to")
    args = parser.parse_args()

    RAM = Manager(args.host, args.port)
    RAM.start()
