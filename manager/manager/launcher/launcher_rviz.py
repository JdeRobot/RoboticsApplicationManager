from manager.manager.launcher.launcher_interface import ILauncher
from manager.manager.docker_thread.docker_thread import DockerThread
from manager.manager.vnc.vnc_server import Vnc_server
from manager.libs.process_utils import check_gpu_acceleration
import os
import stat
from typing import List, Any


class LauncherRviz(ILauncher):
    display: str
    internal_port: int
    external_port: int
    running: bool = False
    acceptsMsgs: bool = False
    threads: List[Any] = []
    console_vnc: Any = Vnc_server()

    def run(self, config_file, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        if ACCELERATION_ENABLED:
            self.console_vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            # Write display config and start the console
            console_cmd = f"export VGL_DISPLAY={DRI_PATH}; export DISPLAY={self.display}; vglrun ros2 run rviz2 rviz2"
        else:
            self.console_vnc.start_vnc(
                self.display, self.internal_port, self.external_port
            )
            # Write display config and start the console
            console_cmd = f"export DISPLAY={self.display};ros2 run rviz2 rviz2"

        console_thread = DockerThread(console_cmd)
        console_thread.start()
        self.threads.append(console_thread)

        self.running = True

    def pause(self):
        pass

    def unpause(self):
        pass

    def reset(self):
        pass

    def is_running(self):
        return self.running

    def terminate(self):
        self.console_vnc.terminate()
        for thread in self.threads:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
        self.running = False

    def died(self):
        pass
