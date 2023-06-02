from src.manager.manager.launcher.launcher_interface import ILauncher
from src.manager.manager.docker_thread.docker_thread import DockerThread
import time
import os
import stat


class LauncherTeleoperatorRos2(ILauncher):
    model_plugin_port: str
    running = False
    threads = []

    def run(self, callback):
        DRI_PATH = os.path.join("/dev/dri", os.environ.get("DRI_NAME", "card0"))
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)
        
        if (ACCELERATION_ENABLED):
            teleop_cmd = f"export VGL_DISPLAY={DRI_PATH}; vglrun /opt/jderobot/utils/model_teleoperator.py 0.0.0.0 {model_plugin_port}"
        else:
            teleop_cmd = f"/opt/jderobot/utils/model_teleoperator.py 0.0.0.0 {model_plugin_port}"

        print("\n\n LAUNCHING TELEOPERATOR\n\n")
        teleop_thread = DockerThread(teleop_cmd)
        teleop_thread.start()
        self.threads.append(teleop_thread)

        self.running = True
    
    def check_device(self, device_path):
        try:
            return stat.S_ISCHR(os.lstat(device_path)[stat.ST_MODE])
        except:
            return False

    def is_running(self):
        return self.running

    def terminate(self):
        for thread in self.threads:
            thread.terminate()
            thread.join()
        self.running = False

    def died(self):
        pass