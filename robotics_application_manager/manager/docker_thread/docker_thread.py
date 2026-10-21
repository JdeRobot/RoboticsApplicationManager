"""Docker Thread Class"""

import threading
import subprocess
import os
import signal
import sys
import time

import psutil

# Time the process group gets to stop after SIGINT before it is killed
STOP_TIMEOUT = 15.0


def group_alive(pgid):
    """Whether any process of the group is still running, zombies aside"""
    for proc in psutil.process_iter():
        try:
            if os.getpgid(proc.pid) == pgid and proc.status() != psutil.STATUS_ZOMBIE:
                return True
        except (ProcessLookupError, psutil.NoSuchProcess):
            continue
    return False


class DockerThread(threading.Thread):
    """Threaded Docker Thread Class"""

    def __init__(self, cmd, shell=True):
        threading.Thread.__init__(self)
        self.cmd = cmd
        self.process = None
        self.shell = shell

    def run(self):
        self.process = subprocess.Popen(
            self.cmd,
            shell=self.shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            bufsize=1024,
            universal_newlines=True,
            executable="/bin/bash",
        )
        self.process.communicate()

    def terminate(self):
        """Terminates the thread and the process"""
        if self.process:
            try:
                pgid = os.getpgid(self.process.pid)
            except ProcessLookupError as error:
                print(f"{self.process.pid}: Process already terminated {error}")
                return

            # SIGINT lets ros2 launch stop its nodes, SIGTERM makes it exit
            # at once and leaves the nodes still stopping as orphans
            try:
                os.killpg(pgid, signal.SIGINT)
            except ProcessLookupError:
                return

            deadline = time.monotonic() + STOP_TIMEOUT
            while group_alive(pgid) and time.monotonic() < deadline:
                time.sleep(0.1)

            # Orphans keep the group, so this also reaches nodes stuck stopping
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
