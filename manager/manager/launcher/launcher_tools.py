from manager.libs.process_utils import get_class, class_from_module
from typing import Optional
from pydantic import BaseModel


from manager.libs.process_utils import get_class, class_from_module
from manager.ram_logging.log_manager import LogManager
from manager.manager.launcher.launcher_interface import ILauncher

tools = {
    "console": {
        "module": "console",
        "display": ":1",
        "external_port": 6082,
        "internal_port": 5901,
    },
    "gazebo": {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "gazebo",
        "display": ":2",
        "external_port": 6080,
        "internal_port": 5900,
    },
    "gzsim": {
        "type": "module",
        "width": 1024,
        "height": 768,
        "module": "gzsim",
        "display": ":2",
        "external_port": 6080,
        "internal_port": 5900,
    },
    "o3de": {
        "type": "module",
        "module": "o3de",
    },
    "rviz": {
        "module": "rviz",
        "display": ":3",
        "external_port": 6081,
        "internal_port": 5902,
    },
    "web_gui": {
        "type": "module",
        "module": "web_gui",
        "internal_port": 2303,
        "consumer": None,
    },
    "state_monitor": {
        "type": "module",
        "module": "state_monitor",
        "file": "/tmp/tree_state",
        "consumer": None,
    },
    "webcam": {
        "type": "module",
        "module": None,
        "internal_port": 2303,
        "consumer": None,
    },
    "video": {
        "type": "module",
        "module": None,
        "internal_port": 2303,
        "consumer": None,
    },
}

simulator = {
    "gazebo": {"tool": "gazebo"},
    "gz": {"tool": "gzsim"},
    "o3de": {"tool": "o3de"},
}


class LauncherTools(BaseModel):
    module: str = ".".join(__name__.split(".")[:-1])
    world_type: Optional[str] = None
    tools: list[str]
    tools_config: Optional[dict] = None
    launchers: Optional[ILauncher] = []

    def run(self, consumer):
        for tool in self.tools:
            if tool == "simulator":
                if self.world_type is None or self.world_type == "physical":
                    continue
                tool = simulator[self.world_type]["tool"]
            module = tools[tool]
            if module["module"] is None:
                continue
            launcher = self.launch_module(tool, module, consumer)
            self.launchers.append(launcher)

    def terminate(self):
        LogManager.logger.info("Terminating tools launcher")
        for launcher in self.launchers:
            if launcher.is_running():
                launcher.terminate()
        self.launchers = []

    def launch_module(self, name, configuration, consumer):
        def process_terminated(name, exit_code):
            LogManager.logger.info(
                f"LauncherEngine: {name} exited with code {exit_code}"
            )
            if self.terminated_callback is not None:
                self.terminated_callback(name, exit_code)

        # Replace consumer
        if "consumer" in configuration:
            configuration["consumer"] = consumer

        launcher_module_name = configuration["module"]
        launcher_module = f"{self.module}.launcher_{launcher_module_name}.Launcher{class_from_module(launcher_module_name)}"
        launcher_class = get_class(launcher_module)
        config = None
        if self.tools_config is not None and name in self.tools_config:
            config = self.tools_config[name]

        launcher = launcher_class.from_config(launcher_class, configuration)
        launcher.run(config, process_terminated)
        return launcher

    def pause(self):
        for launcher in self.launchers:
            launcher.pause()

    def unpause(self):
        for launcher in self.launchers:
            launcher.unpause()

    def reset(self):
        for launcher in self.launchers:
            launcher.reset()

    def pass_msg(self, data):
        for launcher in self.launchers:
            if launcher.acceptsMsgs:
                launcher.get_msg(data)

    def launch_command(self, configuration):
        pass


class LauncherToolsException(Exception):
    def __init__(self, message):
        super(LauncherToolsException, self).__init__(message)
