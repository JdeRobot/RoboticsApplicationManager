"""Docker Thread Class"""

import threading
import subprocess
import os
import signal
import sys
import psutil


class DockerThread(threading.Thread):
    """Threaded Docker Thread Class"""

    def __init__(self, cmd, shell=True, debug=False):
        threading.Thread.__init__(self)
        self.cmd = cmd
        self.process = None
        self.shell = shell
        self.debug = debug

    def run(self):
        if self.debug:
            self.process = subprocess.Popen(
                self.cmd,
                shell=self.shell,
                stdout=sys.stdout,
                stderr=sys.stdout,
                start_new_session=True,
                bufsize=1024,
                universal_newlines=True,
                executable="/bin/bash",
            )
        else:
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
        self.process_group = os.getpgid(self.process.pid)
        self.process.communicate()

    def terminate(self):
        """Terminates the thread and the process"""
        if self.process:
            try:
                os.killpg(self.process_group, signal.SIGTERM)
            except ProcessLookupError as error:
                print(
                    f"{self.process_group}/{self.process.pid}: Process {self.cmd} already terminated {error}"
                )
