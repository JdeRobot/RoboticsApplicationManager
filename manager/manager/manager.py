from __future__ import annotations
from transitions import Machine

import sys
import signal
import os
import time
import traceback
import zipfile
import json
import base64
from queue import Queue
from uuid import uuid4
import subprocess


from src.manager.manager.launcher.launcher_engine import LauncherEngine
from src.manager.manager.application.robotics_python_application_interface import IRoboticsPythonApplication
from src.manager.libs.process_utils import get_class_from_file
from src.manager.comms.consumer_message import ManagerConsumerMessageException
from src.manager.ram_logging.log_manager import LogManager
from src.manager.comms.new_consumer import ManagerConsumer
from src.manager.libs.process_utils import check_gpu_acceleration






# pylint: disable=unused-argument


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
        {'trigger': 'connect', 'source': 'idle', 'dest': 'connected', 'before': 'on_connect'},
        # Transitions for state connected
        {'trigger': 'launch', 'source': 'connected',
            'dest': 'ready', 'before': 'on_launch'},
        # Transitions for state ready
        {'trigger': 'terminate', 'source': ['ready', 'running', 'paused'],
            'dest': 'connected', 'before': 'on_terminate'},
        {'trigger': 'load', 'source': [
            'ready', 'running', 'paused'], 'dest': 'ready', 'before': 'load_code'},
        {'trigger': 'run', 'source': [
            'ready', 'paused'], 'dest': 'running', 'conditions': 'code_loaded', 'after': 'on_run'},
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
        self.ros_version = self.get_ros_version()
        self.__code_loaded = False
        self.exercise_id = None
        self.machine = Machine(model=self, states=Manager.states, transitions=Manager.transitions,
                               initial='idle', send_event=True, after_state_change=self.state_change)

        self.queue = Queue()

        # TODO: review, hardcoded values
        self.consumer = ManagerConsumer(host, port, self.queue)
        self.launcher = None
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
        self.consumer.send_message({'radi_version': subprocess.check_output(['bash', '-c', 'echo $IMAGE_TAG']), 'ros_version' : subprocess.check_output(['bash', '-c', 'echo $ROS_DISTRO']), 'gpu_avaliable': check_gpu_acceleration(),}, command="introspection")

    def on_stop(self, event):
        self.application.stop()

    def on_launch(self, event):
        """
        Transition executed on launch trigger activ
        """
        def terminated_callback(name, code):
            # TODO: Prototype, review this callback
            LogManager.logger.info(
                f"Manager: Launcher {name} died with code {code}")
            if self.state != 'ready':
                self.terminate()

        configuration = event.kwargs.get('data', {})
        configuration['ros_version'] = self.ros_version

        # generate exercise_folder environment variable
        self.exercise_id = configuration['exercise_id']
        os.environ["EXERCISE_FOLDER"] = f"{os.environ.get('EXERCISES_STATIC_FILES')}/{self.exercise_id}"

        # Check if application and launchers configuration is missing
        # TODO: Maybe encapsulate configuration as a data class with validation?
        application_configuration = configuration.get('application', None)
        if application_configuration is None:
            raise Exception("Application configuration missing")

        # check if launchers configuration is missing
        launchers_configuration = configuration.get('launch', None)
        if launchers_configuration is None:
            raise Exception("Launch configuration missing")

        # check if launch files are sent
        launch_files = configuration.get('launch_files', None)
        if (launch_files is not None):
            try:
                # Convert base64 to binary
                binary_content = base64.b64decode(launch_files)
                # Save the binary content as a file
                with open('workspace/binaries/user_worlds.zip', 'wb') as file:
                    file.write(binary_content)
                # Unzip the file
                with zipfile.ZipFile('workspace/binaries/user_worlds.zip', 'r') as zip_ref:
                    zip_ref.extractall('workspace/worlds/')
            except Exception as e:
                print("An error occurred while opening zip_path as r:" + str(e))

        LogManager.logger.info(
            f"Launch transition started, configuration: {configuration}")

        # configuration['terminated_callback'] = terminated_callback
        self.launcher = LauncherEngine(**configuration)
        self.launcher.run()

        # TODO: launch application
        application_file = application_configuration['entry_point']
        params = application_configuration.get('params', None)
        application_module = os.path.expandvars(application_file)
        application_class = get_class_from_file(application_module, "Exercise")

        if not issubclass(application_class, IRoboticsPythonApplication):
            self.launcher.terminate()
            raise Exception(
                "The application must be an instance of IRoboticsPythonApplication")
        params['update_callback'] = self.update
        self.application = application_class(**params)
        """  time.sleep(1)
        self.application.pause() """

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

    def on_enter_connected(self, event):
        LogManager.logger.info("Connect state entered")

    def on_run(self, event):
        if self.code_loaded:
            self.application.run()

    def on_enter_ready(self, event):
        configuration = event.kwargs.get('data', {})
        LogManager.logger.info(
            f"Start state entered, configuration: {configuration}")

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
                file.write("An error occurred while opening zip_path as r:" + str(e))
        
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

    def get_ros_version(self):
        output = subprocess.check_output(['bash', '-c', 'echo $ROS_VERSION'])
        return output.decode('utf-8')[0]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "host", type=str, help="Host to listen to  (0.0.0.0 or all hosts)")
    parser.add_argument("port", type=int, help="Port to listen to")
    args = parser.parse_args()

    RAM = Manager(args.host, args.port)
    RAM.start()
