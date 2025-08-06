from manager.manager.launcher.launcher_interface import ILauncher
from manager.manager.docker_thread.docker_thread import DockerThread
import time
import os
import stat


class LauncherTeleoperatorRos2(ILauncher):
    running = False
    threads = []

    def run(self, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        if ACCELERATION_ENABLED:
            teleop_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun python3 /opt/jderobot/utils/model_teleoperator.py 0.0.0.0"
        else:
            teleop_cmd = f"python3 /opt/jderobot/utils/model_teleoperator.py 0.0.0.0"

        teleop_thread = DockerThread(teleop_cmd)
        teleop_thread.start()
        self.threads.append(teleop_thread)

        self.running = True

    def is_running(self):
        return self.running

    def terminate(self):
        for thread in self.threads:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
        self.running = False

    def died(self):
        pass
