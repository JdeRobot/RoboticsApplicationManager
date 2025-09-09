"""VNC server management module for RoboticsApplicationManager.

Provides classes and functions to start and manage VNC and noVNC servers,
including GPU-accelerated sessions and desktop icon creation.
"""

import time
import socket
from manager.manager.docker_thread.docker_thread import DockerThread
import subprocess
from typing import List, Any
import os
from manager.libs.process_utils import wait_for_xserver


class Vnc_server:
    """Class to manage VNC and noVNC server sessions for RoboticsApplicationManager."""

    threads: List[Any] = []
    running: bool = False

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
        turbovnc_thread = DockerThread(turbovnc_cmd)
        turbovnc_thread.start()
        self.threads.append(turbovnc_thread)
        wait_for_xserver(display)

        # Start noVNC with default port 6080 listening to VNC server on 5900
        if self.get_ros_version() == "2":
            novnc_cmd = (
                f"/noVNC/utils/novnc_proxy --listen {external_port} "
                f"--vnc localhost:{internal_port}"
            )
        else:
            novnc_cmd = (
                f"/noVNC/utils/launch.sh --listen {external_port} "
                f"--vnc localhost:{internal_port}"
            )

        novnc_thread = DockerThread(novnc_cmd)
        novnc_thread.start()
        self.threads.append(novnc_thread)
        self.running = True

        self.wait_for_port("localhost", internal_port)
        self.wait_for_port("localhost", external_port)

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
        turbovnc_thread = DockerThread(turbovnc_cmd)
        turbovnc_thread.start()
        self.threads.append(turbovnc_thread)
        wait_for_xserver(display)

        # Start noVNC with default port 6080 listening to VNC server on 5900
        if self.get_ros_version() == "2":
            novnc_cmd = (
                f"/noVNC/utils/novnc_proxy --listen {external_port} "
                f"--vnc localhost:{internal_port}"
            )
        else:
            novnc_cmd = (
                f"/noVNC/utils/launch.sh --listen {external_port} "
                f"--vnc localhost:{internal_port}"
            )

        novnc_thread = DockerThread(novnc_cmd)
        novnc_thread.start()
        self.threads.append(novnc_thread)
        self.running = True

        self.wait_for_port("localhost", internal_port)
        self.wait_for_port("localhost", external_port)

    def wait_for_port(self, host, port, timeout=20):
        """Wait for a TCP port on a host to become available within a timeout period.

        Args:
            host (str): Hostname or IP address to check.
            port (int): Port number to check.
            timeout (int, optional): Maximum time to wait in seconds. Defaults to 20.

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
        for thread in self.threads:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
        self.running = False

    def get_ros_version(self):
        """Get the current ROS version from the environment.

        Returns:
            str: The ROS version as a string.
        """
        output = subprocess.check_output(["bash", "-c", "echo $ROS_VERSION"])
        return output.decode("utf-8").strip()

    def create_desktop_icon(self):
        """Create a desktop icon to launch a terminal application."""
        try:
            desktop_dir = os.path.expanduser("~/Desktop")
            if not os.path.exists(desktop_dir):
                os.makedirs(desktop_dir)
            desktop_path = os.path.join(desktop_dir, "terminal_launcher.desktop")
            with open(desktop_path, "w") as f:
                f.write(
                    """[Desktop Entry]
                    Name=Open Terminal
                    Exec=xterm
                    Icon=utilities-terminal
                    Type=Application
                    Encoding=UTF-8
                    Terminal=false
                    Categories=None;"""
                )
            os.chmod(desktop_path, 0o755)
        except Exception as err:
            print(err)

    def create_gzclient_icon(self):
        """Create a desktop icon to launch the Gazebo client application."""
        desktop_dir = os.path.expanduser("~/Desktop")
        if not os.path.exists(desktop_dir):
            os.makedirs(desktop_dir)
        desktop_path = os.path.join(desktop_dir, "gzclient_launcher.desktop")

        try:
            with open(desktop_path, "w") as f:
                f.write(
                    """[Desktop Entry]
    Name=Gazebo Client
    Exec=gzclient
    Icon=gazebo
    Type=Application
    Encoding=UTF-8
    Terminal=false
    Categories=None;"""
                )
            os.chmod(desktop_path, 0o755)
            print("Icono de gzclient creado con éxito en el escritorio.")
        except Exception as e:
            print(f"Error al crear el icono de gzclient: {e}")
