"""Utilities for testing the manager state transitions."""

import builtins
import io


def setup_manager_to_connected(manager, monkeypatch):
    """Move manager to connected state."""
    manager.trigger("connect", event=None)
    assert manager.state == "connected"


def setup_manager_to_world_ready(manager, monkeypatch):
    """Move manager to world_ready state."""

    setup_manager_to_connected(manager, monkeypatch)

    # Use ConfigurationModel for valid world config
    from manager.libs.launch_world_model import ConfigurationModel

    valid_world_cfg = ConfigurationModel(
        world="test_world", launch_file_path="/path/to/launch_file.launch"
    ).model_dump()

    event_data = {
        "world": valid_world_cfg,
        "robot": {
            "world": None,  # No robot specified
            "robot_config": {"name": "test_robot", "type": "simple"},
        },
    }
    manager.trigger("launch_world", data=event_data)

    # State should now be 'world_ready'
    assert manager.state == "world_ready"

    # Patch LauncherWorld to avoid starting real worlds
    class DummyConsumer:
        def __init__(self):
            self.launched = False

        def consume(self, *args, **kwargs):
            pass

    class DummyLauncherWorld:
        def __init__(self, *args, **kwargs):
            self.launched = False


def setup_manager_to_visualization_ready(manager, monkeypatch):
    """Move manager to visualization_ready state."""

    # Move to 'world_ready' state first
    setup_manager_to_world_ready(manager, monkeypatch)

    # Trigger visualization ready state
    manager.trigger(
        "prepare_visualization",
        data={
            "type": "gazebo_rae",
            "file": "test_file",
        },
    )

    assert manager.state == "visualization_ready"


def setup_manager_to_application_running(manager, monkeypatch):
    """Move manager to application_running state."""

    setup_manager_to_visualization_ready(manager, monkeypatch)

    class DummyProc:
        def __init__(self):
            self.pid = 123

        def kill(self):
            pass

        def suspend(self):
            pass

    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/workspace/code/app.zip":
            if "w" in mode:
                return io.BytesIO()
            elif "r" in mode:
                return io.BytesIO(b"fake zip content")
        return original_open(file, mode, *args, **kwargs)

    # Mock file system and subprocess operations
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.listdir", lambda path: ["0", "1", "2"])
    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: DummyProc())
    monkeypatch.setattr("os.mkdir", lambda path: None)
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    monkeypatch.setattr(
        "zipfile.ZipFile",
        lambda *a, **k: type(
            "Zip",
            (),
            {"extractall": lambda self, path: None, "close": lambda self: None},
        )(),
    )
    monkeypatch.setattr("base64.b64decode", lambda s: b"print('hello')")
    monkeypatch.setattr(
        "manager.manager.manager.Manager.unpause_sim", lambda self: None
    )
    # Mock linter to return no errors
    manager.linter.evaluate_code = lambda code, ros_version: ""
    # Trigger application running state
    manager.trigger(
        "run_application",
        data={"type": "robotics-academy", "code": "data:base64,ZmFrZV9jb2Rl"},
    )
    # Assert state is now application_running
    assert manager.state == "application_running"

    # Ensure application process is not None
    manager.application_process = DummyProc()
