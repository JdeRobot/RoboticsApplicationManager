import os
import stat

from pydantic import BaseModel


class ILauncher(BaseModel):
    def run(self, callback: callable):
        raise NotImplemented("Launcher must implement run method")

    def is_running(self):
        raise NotImplemented("Launcher must implement run method")

    def terminate(self):
        raise NotImplemented("Launcher must implement run method")

    def died(self, callback):
        raise NotImplemented("Launcher must implement run method")

    def from_config(cls, config):
        obj = cls(**config)
        return obj

    @staticmethod
    def get_dri_path():
        # If DRI_NAME is not set, set DRI_PATH to None
        dri_name = os.environ.get("DRI_NAME")
        dri_path = os.path.join("/dev/dri", dri_name) if dri_name else None
        return dri_path

    @staticmethod
    def check_device(device_path):
        try:
            return stat.S_ISCHR(os.lstat(device_path)[stat.ST_MODE])
        except:
            return False


class LauncherException(Exception):
    def __init__(self, message):
        super(LauncherException, self).__init__(message)
