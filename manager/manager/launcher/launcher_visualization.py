from src.manager.libs.process_utils import get_class, class_from_module
from typing import Optional
from pydantic import BaseModel


from src.manager.libs.process_utils import get_class, class_from_module, get_ros_version
from src.manager.ram_logging.log_manager import LogManager
from src.manager.manager.launcher.launcher_interface import ILauncher


visualization = {
    "none": [],
    "console": [{"module": "console",
                 "display": ":1",
                 "external_port": 1108,
                 "internal_port": 5901}],
    "gazebo_gra": [{
        "type": "module",
        "module": "console",
        "display": ":1",
        "external_port": 1108,
        "internal_port": 5901},
        {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "gazebo_view",
        "display": ":2",
        "external_port": 6080,
        "internal_port": 5900
    },
        {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "robot_display_view",
        "display": ":3",
        "external_port": 2303,
        "internal_port": 5902
    }
    ],
    "gazebo_rae": [{"type": "module",
                            "module": "console",
                            "display": ":1",
                            "external_port": 1108,
                            "internal_port": 5901},
                   {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "gazebo_view",
        "display": ":2",
        "external_port": 6080,
        "internal_port": 5900
    }],
    "physic_gra": [{"module": "console",
                    "display": ":1",
                    "external_port": 1108,
                    "internal_port": 5901},
                   {
        "type": "module",
                "width": 1024,
        "height": 768,
        "module": "robot_display_view",
        "display": ":2",
        "external_port": 2303,
        "internal_port": 5902
    }],
    "physic_rae": [{"module": "console",
                    "display": ":1",
                    "external_port": 1108,
                    "internal_port": 5901},
                   {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "robot_display_view",
        "display": ":2",
        "external_port": 2303,
        "internal_port": 5902
    }]
}


class LauncherVisualization(BaseModel):
    module: str = '.'.join(__name__.split('.')[:-1])
    visualization: str
    launcher: Optional[ILauncher] = None

    def run(self):
        for module in visualization[self.visualization]:
            self.launcher = self.launch_module(module)

    def terminate(self):
        if self.launcher is not None and self.launcher.is_running():
            LogManager.logger.info(f"Terminating world launcher")
            self.launcher.terminate()
        self.launcher = None  # Restablecer el lanzador del mundo

    def launch_module(self, configuration):
        def process_terminated(name, exit_code):
            LogManager.logger.info(
                f"LauncherEngine: {name} exited with code {exit_code}")
            if self.terminated_callback is not None:
                self.terminated_callback(name, exit_code)

        launcher_module_name = configuration["module"]
        launcher_module = f"{self.module}.launcher_{launcher_module_name}.Launcher{class_from_module(launcher_module_name)}"
        launcher_class = get_class(launcher_module)
        launcher = launcher_class.from_config(launcher_class, configuration)
        launcher.run(process_terminated)
        return launcher

    def launch_command(self, configuration):
        pass


class LauncherVisualizationException(Exception):
    def __init__(self, message):
        super(LauncherWorldException, self).__init__(message)
