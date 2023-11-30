from __future__ import annotations

import base64
import os
import signal
import subprocess
import sys
import time
import traceback
import zipfile
from queue import Queue
from uuid import uuid4

from transitions import Machine

from src.manager.comms.consumer_message import ManagerConsumerMessageException
from src.manager.comms.new_consumer import ManagerConsumer
from src.manager.libs.process_utils import check_gpu_acceleration, get_user_world
from src.manager.libs.launch_world_model import ConfigurationManager
from src.manager.manager.launcher.launcher_world import LauncherWorld
from src.manager.manager.launcher.launcher_visualization import LauncherVisualization
from src.manager.ram_logging.log_manager import LogManager


class Manager:
    states = [
        "idle",
        "connected",
        "ready",
        "running",
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
        {'trigger': 'prepare_visualiation',
            'source': 'world_ready', 'dest': 'visualization_ready', 'before': 'on_prepare_world'},
        # Transitions for state ready
        {'trigger': 'terminate', 'source': ['ready', 'running', 'paused'],
            'dest': 'connected', 'before': 'on_terminate'},
        {'trigger': 'load', 'source': [
            'ready', 'running', 'paused'], 'dest': 'ready', 'before': 'load_code'},
        {'trigger': 'run', 'source': [
            'visualization_ready', 'paused'], 'dest': 'running', 'conditions': 'code_loaded', 'after': 'on_run'},
        # Transitions for state running
        {'trigger': 'pause', 'source': 'running',
            'dest': 'paused', 'before': 'on_pause'},
        {'trigger': 'stop', 'source': [
            'running', 'paused'], 'dest': 'ready', 'before': 'on_stop'},
        # Global transitions
        {'trigger': 'disconnect', 'source': '*',
            'dest': 'idle', 'before': 'on_disconnect'},
    ]

    def __init__(self, host: str, port: int):
        self.__code_loaded = False
        self.machine = Machine(model=self, states=Manager.states, transitions=Manager.transitions,
                               initial='idle', send_event=True, after_state_change=self.state_change)

        self.queue = Queue()

        # TODO: review, hardcoded values
        self.consumer = ManagerConsumer(host, port, self.queue)
        self.world_launcher = None
        self.visualization_launcher = None
        self.application = None
        self.running = True

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

    def on_stop(self, event):
        self.application.stop()

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

        get_user_world(configuration.launch_file)

        self.world_launcher = LauncherWorld(**configuration.model_dump())
        self.world_launcher.run()
        LogManager.logger.info("Launch transition finished")

        """         # TODO: launch application
                application_file = application_configuration['entry_point']
                params = application_configuration.get('params', None)
                application_module = os.path.expandvars(application_file)
                application_class = get_class_from_file(application_module, "Exercise")

                if not issubclass(application_class, IRoboticsPythonApplication):
                    self.launcher.terminate()
                    raise Exception(
                        "The application must be an instance of IRoboticsPythonApplication")
                params['update_callback'] = self.update
                self.application = application_class(**params) """

    def on_prepare_visualization(self, event):
        visualization_type = event.kwargs.get('data', {})
        self.visualization_launcher = LauncherVisualization(
            **visualization_type)
        self.visualization_launcher.run()
        LogManager.logger.info("Visualization transition finished")

    def on_terminate(self, event):
        """Terminates the application and the launcher \
            and sets the variable __code_loaded to False"""
        try:
            self.application.terminate()
            self.__code_loaded = False
            self.launcher.terminate()
        except Exception:
            LogManager.logger.exception(f"Exception terminating instance")
            print(traceback.format_exc())

    def on_disconnect(self, event):
        try:
            self.consumer.stop()
            self.__code_loaded = False
            self.application.terminate()
            self.launcher.terminate()
        except Exception as e:
            LogManager.logger.exception(f"Exception terminating instance")
            print(traceback.format_exc())
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def on_run(self, event):
        if self.code_loaded:
            self.application.run()

    def load_code(self, event):
        self.application.pause()
        self.__code_loaded = False
        LogManager.logger.info("Internal transition load_code executed")
        message_data = event.kwargs.get('data', {})

        # Code is sent raw
        message_code = message_data.get('code', None)
        if message_code is not None:
            self.application.load_code(message_code)

        # Code is sent zipped
        message_zip = message_data.get('zip', None)
        if message_zip is not None:
            try:
                # Convert base64 to binary
                binary_content = base64.b64decode(message_zip)
                # Save the binary content as a file
                with open('workspace/binaries/user_app.zip', 'wb') as file:
                    file.write(binary_content)
                # Unzip the file
                with zipfile.ZipFile('workspace/binaries/user_app.zip', 'r') as zip_ref:
                    zip_ref.extractall('workspace/code/')
                entrypoint_path = message_data.get('entrypoint', None)
                if (entrypoint_path is not None):
                    entrypoint_path = "/workspace/code/" + entrypoint_path
                    self.application.load_code(entrypoint_path)
            except Exception as e:
                file.write(
                    "An error occurred while opening zip_path as r:" + str(e))

        self.__code_loaded = True

    def code_loaded(self, event):
        return self.__code_loaded

    def process_messsage(self, message):
        self.trigger(message.command, data=message.data or None)
        response = {"message": f"Exercise state changed to {self.state}"}
        self.consumer.send_message(message.response(response))

    def on_pause(self, msg):
        self.application.pause()

    def on_resume(self, msg):
        self.application.resume()

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
            self.application.terminate()
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
                    if message.command == "#gui":
                        self.application.handle_client_gui(message.data)
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
