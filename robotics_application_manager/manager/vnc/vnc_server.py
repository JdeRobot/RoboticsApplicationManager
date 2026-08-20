"""VNC server management module for RoboticsApplicationManager.

Provides classes and functions to start and manage VNC and noVNC servers,
including GPU-accelerated sessions and desktop icon creation.
"""

import os
import signal
import subprocess
import socket
import time
from typing import Any, List

from robotics_application_manager.libs import wait_for_xserver
from robotics_application_manager.manager.docker_thread import DockerThread


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

        certs = ""

        if os.path.isfile("/etc/certs/cert.pem"):
            certs = "--cert /etc/certs/cert.pem --key /etc/certs/privkey.pem"

        # Start noVNC with default port 6080 listening to VNC server on 5900
        if self.get_ros_version() == "2":
            novnc_cmd = (
                f"/noVNC/utils/novnc_proxy --listen {external_port} "
                f"--vnc localhost:{internal_port} "
                f"{certs}"
            )
        else:
            novnc_cmd = (
                f"/noVNC/utils/launch.sh --listen {external_port} "
                f"--vnc localhost:{internal_port} "
                f"{certs}"
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

        certs = ""

        if os.path.isfile("/etc/certs/cert.pem"):
            certs = "--cert /etc/certs/cert.pem --key /etc/certs/privkey.pem"

        # Start noVNC with default port 6080 listening to VNC server on 5900
        if self.get_ros_version() == "2":
            novnc_cmd = (
                f"/noVNC/utils/novnc_proxy --listen {external_port} "
                f"--vnc localhost:{internal_port} "
                f"{certs}"
            )
        else:
            novnc_cmd = (
                f"/noVNC/utils/launch.sh --listen {external_port} "
                f"--vnc localhost:{internal_port} "
                f"{certs}"
            )

        novnc_thread = DockerThread(novnc_cmd)
        novnc_thread.start()
        self.threads.append(novnc_thread)
        self.running = True

        self.wait_for_port("localhost", internal_port)
        self.wait_for_port("localhost", external_port)

    def start_vnc_wsl(self, display, internal_port, external_port):
        """Start the WSL2 Xvfb, x11vnc, and noVNC backend."""
        self.wsl_processes = []

        try:
            self._start_wsl_process(["Xvfb", display, "-screen", "0", "1920x1080x24"])
            wait_for_xserver(display)

            self._start_wsl_process(
                [
                    "x11vnc",
                    "-display",
                    display,
                    "-rfbport",
                    str(internal_port),
                    "-nopw",
                    "-forever",
                    "-noxdamage",
                    "-shared",
                ]
            )

            novnc_cmd = [
                "/noVNC/utils/novnc_proxy",
                "--listen",
                str(external_port),
                "--vnc",
                f"localhost:{internal_port}",
                "--web",
                "/noVNC",
            ]
            if os.path.isfile("/etc/certs/cert.pem"):
                novnc_cmd += [
                    "--cert",
                    "/etc/certs/cert.pem",
                    "--key",
                    "/etc/certs/privkey.pem",
                ]

            self._start_wsl_process(novnc_cmd)
            self.wait_for_port("localhost", internal_port)
            self.wait_for_port("localhost", external_port)
            self.running = True
        except Exception:
            self.terminate_wsl_processes()
            raise

    def _start_wsl_process(self, command):
        """Start and track one WSL VNC process."""
        self.wsl_processes.append(
            subprocess.Popen(
                command,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )

    def terminate_wsl_processes(self):
        """Terminate only the processes started by the WSL2 VNC backend."""
        for process in reversed(getattr(self, "wsl_processes", [])):
            if process.poll() is None:
                try:
                    process_group = os.getpgid(process.pid)
                    os.killpg(process_group, signal.SIGTERM)
                    process.wait(timeout=10)
                except ProcessLookupError:
                    continue
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process_group, signal.SIGKILL)
                    except ProcessLookupError:
                        continue
                    process.wait()
        self.wsl_processes = []

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
        self.terminate_wsl_processes()
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
                f.write("""[Desktop Entry]
                    Name=Open Terminal
                    Exec=xterm
                    Icon=utilities-terminal
                    Type=Application
                    Encoding=UTF-8
                    Terminal=false
                    Categories=None;""")
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
                f.write("""[Desktop Entry]
    Name=Gazebo Client
    Exec=gzclient
    Icon=gazebo
    Type=Application
    Encoding=UTF-8
    Terminal=false
    Categories=None;""")
            os.chmod(desktop_path, 0o755)
            print("Icono de gzclient creado con éxito en el escritorio.")
        except Exception as e:
            print(f"Error al crear el icono de gzclient: {e}")
