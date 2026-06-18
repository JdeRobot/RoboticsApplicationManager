import sys
from .launcher_interface import ILauncher
from robotics_application_manager.manager.docker_thread import DockerThread
from robotics_application_manager.manager.vnc import Vnc_server
from robotics_application_manager.libs import (
    wait_for_process_to_start,
    check_gpu_acceleration,
)
import subprocess
import time
import os
import stat
from typing import List, Any
from robotics_application_manager import LogManager

from gz.msgs10.world_control_pb2 import WorldControl
from gz.msgs10.world_reset_pb2 import WorldReset
from gz.msgs10.entity_pb2 import Entity
from gz.msgs10.boolean_pb2 import Boolean
from gz.transport13 import Node


def call_gzservice(service, reqtype, reptype, timeout, req):
    command = f"gz service -s {service} --reqtype {reqtype} --reptype {reptype} --timeout {timeout} --req '{req}'"
    try:
        p = subprocess.Popen(
            [
                f"{command}",
            ],
            shell=True,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            bufsize=1024,
            universal_newlines=True,
        )
        p.wait(10)
    except:
        p.kill()

        LogManager.logger.exception(f"Unable to complete call: {service}")
        raise Exception(f"Unable to complete call: {service}")


def call_service(service, service_type, request_data="{}"):
    command = f"ros2 service call {service} {service_type} '{request_data}'"
    try:
        p = subprocess.Popen(
            [
                f"{command}",
            ],
            shell=True,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            bufsize=1024,
            universal_newlines=True,
        )
        p.wait(10)
    except:
        p.kill()

        LogManager.logger.exception(f"Unable to complete call: {service}")
        raise Exception(f"Unable to complete call: {service}")


def is_ros_service_available(service_name):
    try:
        result = subprocess.run(
            ["ros2", "service", "list", "--include-hidden-services"],
            capture_output=True,
            text=True,
            check=True,
        )
        return service_name in result.stdout
    except subprocess.CalledProcessError as e:
        LogManager.logger.exception(f"Error checking service availability: {e}")
        return False


class LauncherGzsim(ILauncher):
    display: str
    internal_port: int
    external_port: int
    height: int
    width: int
    running: bool = False
    threads: List[Any] = []
    acceptsMsgs: bool = False
    gz_vnc: Any = Vnc_server()

    def run(self, config_file, callback):
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        if config_file is None:
            config_file = "/opt/jderobot/Launchers/visualization/default.config"

        # Configure browser screen width and height for gz GUI
        gzclient_config_cmds = f"sed -i 's/<width>.*<\/width>/<width>{self.width}<\/width>/; s/<height>.*<\/height>/<height>{self.height}<\/height>/' {config_file};"

        if ACCELERATION_ENABLED:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            # Write display config and start gzclient
            gzclient_cmd = f"export DISPLAY={self.display}; {gzclient_config_cmds} export VGL_DISPLAY={DRI_PATH}; vglrun gz sim -g -v4 --gui-config {config_file}"
        else:
            # Starts xserver, x11vnc and novnc
            self.gz_vnc.start_vnc(self.display, self.internal_port, self.external_port)
            # Write display config and start gzclient
            gzclient_cmd = f"export DISPLAY={self.display}; {gzclient_config_cmds} gz sim -g -v4 --gui-config {config_file}"

        gzclient_thread = DockerThread(gzclient_cmd)
        gzclient_thread.start()
        self.threads.append(gzclient_thread)

        process_name = "gz sim"
        wait_for_process_to_start(process_name, timeout=60)

        self.running = True

    def check_device(self, device_path):
        try:
            return stat.S_ISCHR(os.lstat(device_path)[stat.ST_MODE])
        except:
            return False

    def is_running(self):
        return self.running

    def terminate(self):
        self.gz_vnc.terminate()
        for thread in self.threads:
            thread.terminate()
            thread.join()
        self.running = False

    def died(self):
        pass

    def pause(self):
        call_gzservice(
            "/world/default/control",
            "gz.msgs.WorldControl",
            "gz.msgs.Boolean",
            "3000",
            "pause: true",
        )

    def unpause(self):
        call_gzservice(
            "/world/default/control",
            "gz.msgs.WorldControl",
            "gz.msgs.Boolean",
            "3000",
            "pause: false",
        )

    def reset(self, robot_entity=None):
        if is_ros_service_available("/drone0/platform/state_machine/_reset"):
            call_service(
                "/drone0/platform/state_machine/_reset",
                "std_srvs/srv/Trigger",
                "{}",
            )
        node = Node()

        node.request(
            f"/world/default/control",
            WorldControl(pause=True),
            WorldControl,
            Boolean,
            10000,
        )

        if robot_entity is not None:
            node.request(
                f"/world/default/remove",
                Entity(name=robot_entity, type=Entity.MODEL),
                Entity,
                Boolean,
                5000,
            )

        node.request(
            f"/world/default/control",
            WorldControl(pause=True, reset=WorldReset(all=True)),
            WorldControl,
            Boolean,
            10000,
        )

        if is_ros_service_available("/drone0/controller/_reset"):
            call_service("/drone0/controller/_reset", "std_srvs/srv/Trigger", "{}")

    def get_dri_path(self):
        directory_path = "/dev/dri"
        dri_path = ""
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            files = os.listdir(directory_path)
            if "card1" in files:
                dri_path = os.path.join("/dev/dri", os.environ.get("DRI_NAME", "card1"))
            else:
                dri_path = os.path.join("/dev/dri", os.environ.get("DRI_NAME", "card0"))
        return dri_path
