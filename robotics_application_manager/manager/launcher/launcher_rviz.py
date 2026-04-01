"""
RViz Visualization Launcher for ROS 2.

Handles the initialization and lifecycle of the ROS 2 Visualization tool (RViz).
Orchestrates the loading of .rviz configuration files and manages the X11
display environment to project sensor data (Lidar, Cameras, TF frames)
to the web frontend.
"""

from .launcher_interface import ILauncher
from robotics_application_manager.manager.docker_thread import DockerThread
from robotics_application_manager.manager.vnc import Vnc_server
from robotics_application_manager.libs import check_gpu_acceleration
import os
import stat
from typing import List, Any


class LauncherRviz(ILauncher):
    display: str
    internal_port: int
    external_port: int
    running: bool = False
    acceptsMsgs: bool = False
    threads: List[Any] = []
    console_vnc: Any = Vnc_server()

    def run(self, config_file, callback):
        """
        Launches an RViz instance with a specific display configuration.

        Args:
            config_file (str): Path to the .rviz file defining the
                               displays and robot model.
            callback (function): Lifecycle state-change callback.
        """
        DRI_PATH = self.get_dri_path()
        ACCELERATION_ENABLED = self.check_device(DRI_PATH)

        config = "ros2 run rviz2 rviz2"

        if config_file != None:
            config = f"ros2 launch {config_file}"

        print(config)
        if ACCELERATION_ENABLED:
            self.console_vnc.start_vnc_gpu(
                self.display, self.internal_port, self.external_port, DRI_PATH
            )
            # Write display config and start the console
            console_cmd = f"export VGL_DISPLAY={DRI_PATH}; export DISPLAY={self.display}; vglrun {config}"
        else:
            self.console_vnc.start_vnc(
                self.display, self.internal_port, self.external_port
            )
            # Write display config and start the console
            console_cmd = f"export DISPLAY={self.display};{config}"

        console_thread = DockerThread(console_cmd)
        console_thread.start()
        self.threads.append(console_thread)

        self.running = True

    def pause(self):
        pass

    def unpause(self):
        pass

    def reset(self):
        pass

    def is_running(self):
        return self.running

    def terminate(self):
        self.console_vnc.terminate()
        for thread in self.threads:
            if thread.is_alive():
                thread.terminate()
                thread.join()
            self.threads.remove(thread)
        self.running = False

    def died(self):
        pass

    # rviz_node_full = Node(
    #     package="rviz2",
    #     executable="rviz2",
    #     name="rviz2",
    #     output="log",
    #     arguments=["-d", rviz_full_config],
    #     parameters=[
    #         robot_description,
    #         robot_description_semantic,
    #         kinematics_yaml,

    #         pilz_planning_pipeline_config,

    #         joint_limits,
    #         pilz_cartesian_limits,

    #         trajectory_execution,
    #         moveit_controllers,
    #         planning_scene_monitor_parameters,
    #         move_group_capabilities,
    #         {"use_sim_time": True},
    #     ]
    # )
