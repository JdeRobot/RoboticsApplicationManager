"""
RQT Launcher for ROS 2.

Handles the initialization and lifecycle of the ROS 2 Qt GUI framework (RQT).
Loads a .perspective file with the plugins to show (node graph, topics and
TF tree) and manages the X11 display environment to project the
interface to the web frontend.
"""

from .launcher_interface import ILauncher
from robotics_application_manager.manager.docker_thread import DockerThread
from robotics_application_manager.manager.vnc import Vnc_server
from robotics_application_manager import LogManager
from typing import List, Any
import os
import subprocess


class LauncherRqt(ILauncher):
    display: str
    internal_port: int
    external_port: int
    running: bool = False
    acceptsMsgs: bool = False
    threads: List[Any] = []
    vnc: Any = Vnc_server()

    def run(self, config_file, callback):
        """
        Launches an RQT instance with a specific perspective.

        Args:
            config_file (str): Path to the .perspective file defining the
                               plugins and their layout.
            callback (function): Lifecycle state-change callback.
        """
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        if config_file is None:
            config_file = "/opt/jderobot/Launchers/rqt/default.perspective"

        # Keep the graph plugins refreshed and fitted to the browser panel
        autorefresh = os.path.join(os.path.dirname(__file__), "rqt_autorefresh.py")
        config = f"python3 {autorefresh} --perspective-file {config_file}"

        if ACCELERATION_ENABLED:
            self.vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            rqt_cmd = f"export VGL_DISPLAY={DRI_PATH}; export DISPLAY={self.display}; vglrun {config}"
        else:
            self.vnc.start_vnc(self.display, self.internal_port, self.external_port)
            rqt_cmd = f"export DISPLAY={self.display};{config}"

        rqt_thread = DockerThread(rqt_cmd)
        rqt_thread.start()

        self.threads.append(rqt_thread)
        self.running = True

    def pause(self):
        pass

    def unpause(self):
        pass

    def reset(self, robot_entities=[]):
        pass

    def is_running(self):
        return self.running

    def terminate(self):
        LogManager.logger.info(f"Terminating rqt tool")
        self.vnc.terminate()
        for thread in self.threads[:]:
            if thread.is_alive():
                thread.terminate()
                # rqt ignores SIGTERM so join would block forever
                subprocess.call(
                    "pkill -9 -f rqt_autorefresh.py",
                    shell=True,
                    stdout=subprocess.PIPE,
                    bufsize=1024,
                    universal_newlines=True,
                )
                thread.join()
            self.threads.remove(thread)
        self.running = False

    def died(self):
        pass
