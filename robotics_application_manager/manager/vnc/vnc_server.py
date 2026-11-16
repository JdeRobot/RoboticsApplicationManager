"""VNC server management module for RoboticsApplicationManager.

Provides classes and functions to start and manage VNC and noVNC servers,
including GPU-accelerated sessions and desktop icon creation.
"""

import time
import socket
from robotics_application_manager.manager.docker_thread import DockerThread
import subprocess
from typing import List, Any
import os
from robotics_application_manager.libs import wait_for_xserver


class Vnc_server:
    """Class to manage VNC and noVNC server sessions for RoboticsApplicationManager."""

    threads: List[Any] = []
    running: bool = False

    def start(self, display, internal_port, external_port, vnc_cmd):
        turbovnc_thread = DockerThread(vnc_cmd)
        turbovnc_thread.start()
        self.threads.append(turbovnc_thread)
        wait_for_xserver(display)

        certs = ""

        if os.path.isfile("/etc/certs/cert.pem"):
            certs = "--cert /etc/certs/cert.pem --key /etc/certs/privkey.pem"

        # Start noVNC with default port 6080 listening to VNC server on 5900
        novnc_cmd = (
            f"/noVNC/utils/novnc_proxy --listen {external_port} "
            f"--vnc localhost:{internal_port} "
            f"{certs}"
        )

        novnc_thread = DockerThread(novnc_cmd)
        novnc_thread.start()
        self.threads.append(novnc_thread)
        self.running = True

        self.wait_for_port("localhost", internal_port)
        self.wait_for_port("localhost", external_port)

    def start_vnc(self, display, internal_port, external_port):
        """Start a VNC and noVNC server session.

        Args:
            display (str): X display identifier.
            internal_port (int): Port for the VNC server.
            external_port (int): Port for the noVNC server.
        """
        # Start X and VNC servers
        turbovnc_cmd = (
            f"export TVNC_WM=startlxde && "
            f"/opt/TurboVNC/bin/vncserver {display} "
            f"-geometry '1920x1080' -noreset "
            f"-SecurityTypes None -rfbport {internal_port}"
        )
        self.start(display, internal_port, external_port, turbovnc_cmd)

    def start_vnc_gpu(self, display, internal_port, external_port, dri_path):
        """Start a GPU-accelerated VNC and noVNC server session.

        Args:
            display (str): X display identifier.
            internal_port (int): Port for the VNC server.
            external_port (int): Port for the noVNC server.
            dri_path (str): Path to the GPU device for hardware acceleration.
        """
        # Start X and VNC servers
        turbovnc_cmd = (
            f"export VGL_DISPLAY={dri_path} && "
            f"export TVNC_WM=startlxde && "
            f"/opt/TurboVNC/bin/vncserver {display} "
            f"-geometry '1920x1080' -vgl -noreset "
            f"-SecurityTypes None -rfbport {internal_port}"
        )
        self.start(display, internal_port, external_port, turbovnc_cmd)

    def wait_for_port(self, host, port, timeout=120):
        """Wait for a TCP port on a host to become available within a timeout period.

        Args:
            host (str): Hostname or IP address to check.
            port (int): Port number to check.
            timeout (int, optional): Maximum time to wait in seconds. Defaults to 120.

        Raises:
            TimeoutError: If the port does not become available within the timeout.
        """
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    (
                        f"Port {port} on {host} didn't become available "
                        f"within {timeout} seconds."
                    )
                )
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect((host, port))
                break
            except (ConnectionRefusedError, TimeoutError):
                time.sleep(1)

    def is_running(self):
        """Check if the VNC server is currently running.

        Returns:
            bool: True if running, False otherwise.
        """
        return self.running

    def terminate(self):
        """Terminate all running threads and stop the VNC server."""
        for thread in self.threads[:]:
            thread.terminate()
            thread.join()
            self.threads.remove(thread)
        self.running = False
