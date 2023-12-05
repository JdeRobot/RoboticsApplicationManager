import json
import logging
import os.path
import subprocess
import sys
import threading
import time
import rosservice
from threading import Thread

from src.manager.libs.applications.compatibility.client import Client
from src.manager.libs.process_utils import stop_process_and_children
from src.manager.ram_logging.log_manager import LogManager
from src.manager.manager.application.robotics_python_application_interface import IRoboticsPythonApplication
from src.manager.manager.lint.linter import Lint


class CompatibilityExerciseWrapper(IRoboticsPythonApplication):
    def __init__(self, exercise_command, gui_command, update_callback):
        super().__init__(update_callback)
        home_dir = os.path.expanduser('~')
        self.running = False
        self.linter = Lint()
        self.brain_ready_event = threading.Event()
        self.exercise_command = exercise_command
        self.gui_command = gui_command
        self.update_callback = update_callback
        self.pick = None
        self.exercise_server = None
        self.gui_server = None
        self.exercise_connection = None
        self.gui_connection = None
        self._run_exercise_server(
            f"python {self.exercise_command}", f'{home_dir}/ws_code.log', 'websocket_code=ready')
        # TODO: review hardcoded values

    def send_freq(self, exercise_connection, is_alive):
        """Send the frequency of the brain and gui to the exercise server"""
        while self.running:
            if exercise_connection.client.sock.connected:
                exercise_connection.send(
                    """#freq{"brain": 20, "gui": 10, "rtf": 100}""")
                time.sleep(1)

    def save_pick(self, pick):
        self.pick = pick

    def send_pick(self, pick):
        self.gui_connection.send("#pick" + json.dumps(pick))
        print("#pick" + json.dumps(pick))

    def handle_client_gui(self, msg):
        if msg['msg'] == "#pick":
            self.pick = msg['data']
        else:
            self.gui_connection.send(msg['msg'])

    def start_send_freq_thread(self):
        """Start a thread to send the frequency of the brain and gui to the exercise server"""
        self.running = True
        self.send_freq_thread = Thread(target=lambda: self.send_freq(self.exercise_connection,
                                                                     lambda: self.is_alive), daemon=False, name='Monitor frequencies')
        self.send_freq_thread.start()

    def stop_send_freq_thread(self):
        """Stop the thread sending the frequency of the brain and gui to the exercise server"""
        if self.running:
            self.running = False
            self.send_freq_thread.join()

    def _run_exercise_server(self, cmd, log_file, load_string, timeout: int = 5):
        process = subprocess.Popen(f"{cmd}", shell=True, stdout=sys.stdout, stderr=subprocess.STDOUT,
                                   bufsize=1024, universal_newlines=True)

        process_ready = False
        while not process_ready:
            try:
                f = open(log_file, "r")
                if f.readline() == load_string:
                    process_ready = True
                f.close()
                time.sleep(0.2)
            except Exception as e:
                LogManager.logger.debug(
                    f"waiting for server string '{load_string}'...")
                time.sleep(0.2)

        return process_ready, process

    def run(self):
        rosservice.call_service("/gazebo/unpause_physics", [])
        self.exercise_connection.send("#play")

    def stop(self):
        rosservice.call_service('/gazebo/pause_physics', [])
        rosservice.call_service("/gazebo/reset_world", [])

    def resume(self):
        rosservice.call_service("/gazebo/unpause_physics", [])

    def pause(self):
        rosservice.call_service('/gazebo/pause_physics', [])

    def restart(self):
        # Terminate current processes
        try:
            self.stop_send_freq_thread()
        except Exception as error:
            pass
        try:
            stop_process_and_children(self.exercise_server)
            stop_process_and_children(self.gui_server)
            self.exercise_connection.stop()
            self.gui_connection.stop()
        except Exception as error:
            pass

        try:
            home_dir = os.path.expanduser('~')
            os.remove(f'{home_dir}/ws_code.log')
            os.remove(f'{home_dir}/ws_gui.log')
        except OSError as error:
            LogManager.logger.error(
                f"Error al eliminar el archivo log: {error}")

        process_ready_exercise, self.exercise_server = self._run_exercise_server(f"python {self.exercise_command}",
                                                                                 f'{home_dir}/ws_code.log',
                                                                                 'websocket_code=ready')
        if process_ready_exercise:
            self.exercise_connection = Client(
                'ws://127.0.0.1:1905', 'exercise', self.server_message)
            self.exercise_connection.start()

        process_ready_gui, self.gui_server = self._run_exercise_server(f"python {self.gui_command}", f'{home_dir}/ws_gui.log',
                                                                       'websocket_gui=ready')
        if process_ready_gui:
            self.gui_connection = Client(
                'ws://127.0.0.1:2303', 'gui', self.server_message)
            self.gui_connection.start()
            if self.pick:
                time.sleep(2)
                self.send_pick(self.pick)

    @property
    def is_alive(self):
        return self.running

    def load_code(self, code: str):
        self.restart()
        self.start_send_freq_thread()
        errors = self.linter.evaluate_code(code)
        if errors == "":
            self.brain_ready_event.clear()
            self.exercise_connection.send(f"#code {code}")
            self.brain_ready_event.wait()
        else:
            raise Exception(errors)

    def terminate(self):
        try:
            self.stop_send_freq_thread()
        except Exception as error:
            LogManager.logger.error(
                f"Error al detener el hilo de frecuencia: {error}")

        if self.exercise_connection is not None:
            try:
                self.exercise_connection.stop()
            except Exception as error:
                LogManager.logger.error(
                    f"Error al detener la conexión del ejercicio: {error}")

        if self.gui_connection is not None:
            try:
                self.gui_connection.stop()
            except Exception as error:
                LogManager.logger.error(
                    f"Error al detener la conexión de la GUI: {error}")

        if self.exercise_server is not None:
            try:
                stop_process_and_children(self.exercise_server)
            except Exception as error:
                LogManager.logger.error(
                    f"Error al detener el servidor de ejercicio: {error}")

        if self.gui_server is not None:
            try:
                stop_process_and_children(self.gui_server)
            except Exception as error:
                LogManager.logger.error(
                    f"Error al detener el servidor de la GUI: {error}")

        self.running = False
