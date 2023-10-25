from typing import List, Any

from pydantic import BaseModel
import time
from src.manager.libs.process_utils import get_class, class_from_module
from src.manager.ram_logging.log_manager import LogManager

worlds = {
            "gazebo": 
                {"1": [{
                    "type": "module",
                    "module": "ros_api",
                    "resource_folders": [],
                    "model_folders": [],
                    "plugin_folders": [],
                    "parameters": [],
                    "launch_file": [],
                }], "2": [{
                    "type": "module",
                    "module": "ros2_api",
                    "resource_folders": [],
                    "model_folders": [],
                    "plugin_folders": [],
                    "parameters": [],      
                    "launch_file": [],
                }]},
            "drones": 
                {"1": [{
                    "type": "module",
                    "module": "drones",
                    "resource_folders": [],
                    "model_folders": [],
                    "plugin_folders": [],
                    "parameters": [],
                    "launch_file": [],
                }], "2": [{
                    "type": "module",
                    "module": "drones_ros2",
                    "resource_folders": [],
                    "model_folders": [],
                    "plugin_folders": [],
                    "parameters": [],      
                    "launch_file": [],
                }]},
            "physical": {}
            }

visualization = {
            "none": [],
            "console": [{"module":"console",
                    "display":":1",
                    "external_port":1108,
                    "internal_port":5901}],
            "gazebo_gra": [{
                    "type":"module",
                    "module":"console",
                    "display":":1",
                    "external_port":1108,
                    "internal_port":5901},
                    {
                    "type":"module",
                    "width":1024,
                    "height":768,
                    "module":"gazebo_view",
                    "display":":2",
                    "external_port":6080,
                    "internal_port":5900
                    },
                    {
                    "type":"module",
                    "width":1024,
                    "height":768,
                    "module":"robot_display_view",
                    "display":":3",
                    "external_port":2303,
                    "internal_port":5902
                    }
                    ],
            "gazebo_rae": [{"type":"module",
                    "module":"console",
                    "display":":1",
                    "external_port":1108,
                    "internal_port":5901},
                    {
                    "type":"module",
                    "width":1024,
                    "height":768,
                    "module":"gazebo_view",
                    "display":":2",
                    "external_port":6080,
                    "internal_port":5900
                        }],
            "physic_gra": [{"module":"console",
                    "display":":1",
                    "external_port":1108,
                    "internal_port":5901},
                    {
                    "type":"module",
                    "width":1024,
                    "height":768,
                    "module":"robot_display_view",
                    "display":":2",
                    "external_port":2303,
                    "internal_port":5902
                    }],
            "physic_rae": [{"module":"console",
                    "display":":1",
                    "external_port":1108,
                    "internal_port":5901},
                    {
                    "type":"module",
                    "width":1024,
                    "height":768,
                    "module":"robot_display_view",
                    "display":":2",
                    "external_port":2303,
                    "internal_port":5902
                    }]     
        }

class LauncherEngine(BaseModel):
    exercise_id: str
    ros_version: int
    launch: dict
    world: str
    resource_folders: str
    model_folders: str
    launch_file: str
    visualization: str
    module:str = '.'.join(__name__.split('.')[:-1])
    terminated_callback: Any = None

    def run(self):
        keys = sorted(self.launch.keys())
        # Launch world
        for module in worlds[self.world][str(self.ros_version)]:
            module["exercise_id"] = self.exercise_id
            module["resource_folders"] = [self.resource_folders]
            module["model_folders"] = [self.model_folders]
            module["launch_file"] = self.launch_file
            launcher = self.launch_module(module)
            self.launch[str(module['module'])] = {'launcher': launcher}
        # Launch plugins
        for key in keys:
            launcher_data = self.launch[key]
            launcher_type = launcher_data['type']

            # extend launcher data with
            # TODO: Review, maybe there's a better way to do this
            launcher_data["exercise_id"] = self.exercise_id

            if launcher_type == "module":
                launcher = self.launch_module(launcher_data)
                self.launch[key]['launcher'] = launcher

                while not launcher.is_running():
                    time.sleep(0.5)
            elif launcher_type == "command":
                self.launch_command(launcher_data)            
            else:
                raise LauncherEngineException(f"Launcher type {launcher_type} not valid")
        # Launch visualization
        for module in visualization[self.visualization]:
            module["exercise_id"] = self.exercise_id
            launcher = self.launch_module(module)
            self.launch[str(module['module'])] = {'launcher': launcher}
        

    def terminate(self):
        keys = sorted(self.launch.keys())
        for key in keys:
            launcher_data = self.launch[key]
            launcher_class = launcher_data.get('launcher', None)
            LogManager.logger.info(f"Terminating {key}")
            if launcher_class is not None and launcher_class.is_running():
                launcher_class.terminate()

    def launch_module(self, configuration):
        def process_terminated(name, exit_code):
            LogManager.logger.info(f"LauncherEngine: {name} exited with code {exit_code}")
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


class LauncherEngineException(Exception):
    def __init__(self, message):
        super(LauncherEngineException, self).__init__(message)
