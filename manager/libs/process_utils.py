# Thanks to https://stackoverflow.com/questions/452969/does-python-have-an-equivalent-to-java-class-forname
# This should be moved to a utils library
import importlib.util
import os.path
import time
import sys
from subprocess import Popen
import subprocess
import stat

import psutil


def get_class(kls):
    parts = kls.split('.')
    module = ".".join(parts[:-1])
    m = __import__(module)
    for comp in parts[1:]:
        m = getattr(m, comp)
    return m


def get_class_from_file(file_path: str, class_name: str):
    spec = importlib.util.spec_from_file_location("application", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{class_name}"] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def class_from_module(module: str):
    """
    Capitalizes a module name to create class name
    """
    return ''.join([s.capitalize() for s in module.split('_')])


def stop_process_and_children(process: Popen, signal: int = 9, timeout: int = None):
    """
    Stops a list of processes waiting for them to stop
    """
    # collect processes to stop
    proc = psutil.Process(process.pid)
    children = proc.children(recursive=True)
    children.append(proc)

    # send signal to processes
    for p in children:
        try:
            p.send_signal(signal)
        except psutil.NoSuchProcess:
            pass

    gone, alive = psutil.wait_procs(children, timeout=timeout)
    return gone, alive


class classproperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()

def singleton(cls):
    instances = {}
    def get_instance():
        if cls not in instances:
            instances[cls] = cls()
        return instances[cls]
    return get_instance()


def is_xserver_running(display):
    """
    Check whether the X server is running on a given display.

    This function checks the existence of a Unix domain socket which X server
    typically creates to communicate with clients. If the socket exists,
    it is assumed that X server is running.s"""
    display_number = display[1:]
    x_socket_path = os.path.join("/tmp/.X11-unix/", f"X{display_number}")
    return os.path.exists(x_socket_path)

def wait_for_xserver(display, timeout=30):
    """
    Wait for the X server to start within a specified timeout period.

    This function continuously checks if the X server is running on the specified
    display by checking the existence of the Unix domain socket associated with the X server.
    It waits until the X server is available or until the timeout is reached, 
    whichever comes first."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_xserver_running(display):
            print(f"Xserver on {display} is running!")
            return
        time.sleep(0.1)
    print(f"Timeout: Xserver on {display} is not available after {timeout} seconds.")

def is_process_running(process_name):
    """
    Check if a process with the specified name is currently running.

    Parameters:
    - process_name (str): The name of the process to check for.
    """
    try:
        process = subprocess.Popen(["pgrep", "-f", process_name], stdout=subprocess.PIPE)
        # Este comando devuelve el PID si existe, o nada si no existe
        process_return = process.communicate()[0]
        return process_return != b''
    except subprocess.CalledProcessError:
        # El proceso no está corriendo
        return False

def wait_for_process_to_start(process_name, timeout=60):
    """
    Wait for a specified process to start for up to a defined timeout.
    Parameters:
    - process_name (str): The name of the process to wait for.
    - timeout (int, optional): The number of seconds to wait before giving up. Default is 60.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_process_running(process_name):
            print(f"{process_name} is running!")
            return True
        time.sleep(1)
    print(f"Timeout: {process_name} did not start within {timeout} seconds.")
    return False

def check_gpu_acceleration():
    DRI_PATH = os.path.join(
            "/dev/dri", os.environ.get("DRI_NAME", "card0"))
    try:
        return stat.S_ISCHR(os.lstat(DRI_PATH)[stat.ST_MODE])
    except Exception as e:
        return False
    