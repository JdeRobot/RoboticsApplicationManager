"""Tests for transitioning Manager from 'connected' to 'world_ready' state."""

import io
import pytest
import builtins
from manager.manager.manager import Manager


class DummyConsumer:
    """A dummy consumer to capture messages sent by the Manager."""

    def __init__(self):
        """
        Initialize the DummyConsumer with empty message storage.

        This constructor sets up the messages list and last_message attribute.
        """
        self.messages = []
        self.last_message = None

    def send_message(self, *args, **kwargs):
        """
        Capture and store a message sent by the Manager.

        Stores the message arguments and updates the last_message attribute.
        """
        self.messages.append((args, kwargs))
        self.last_message = (args, kwargs)


@pytest.fixture
def manager(monkeypatch):
    """Fixture to provide a Manager instance with patched dependencies for testing."""

    # Patch subprocess.check_output for ROS_DISTRO and IMAGE_TAG
    def fake_check_output(cmd, *a, **k):
        if "ROS_DISTRO" in cmd[-1]:
            return b"humble"
        if "IMAGE_TAG" in cmd[-1]:
            return b"test_image_tag"
        return b""

    monkeypatch.setattr("subprocess.check_output", fake_check_output)

    # Patch check_gpu_acceleration where it is used
    monkeypatch.setattr(
        "manager.manager.manager.check_gpu_acceleration", lambda x=None: "OFF"
    )

    # Patch os.makedirs and os.path.isdir to avoid real FS operations
    monkeypatch.setattr("os.makedirs", lambda path, exist_ok=False: None)
    monkeypatch.setattr("os.path.isdir", lambda path: True)

    # Patch LauncherWorld to avoid launching real processes
    class DummyLauncherWorld:
        def __init__(self, *a, **k):
            self.launched = False

        def launch(self):
            self.launched = True

        def run(self):
            self.launched = True
            # Simulate running the world
            return

        def terminate(self):
            pass

    monkeypatch.setattr("manager.manager.manager.LauncherWorld", DummyLauncherWorld)

    # Patch Server and FileWatchdog to avoid starting real servers
    class DummyServer:
        def __init__(self, port, update_callback):
            self.port = port
            self.update_callback = update_callback
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    class DummyFileWatchdog:
        def __init__(self, path, update_callback):
            self.path = path
            self.update_callback = update_callback
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    class DummyVisualizationLauncher:
        def __init__(self, *args, **kwargs):
            self.launchers = []

        def run(self):
            # Simulate running the visualization launcher
            return

        def terminate(self):
            pass

    monkeypatch.setattr(
        "manager.manager.manager.LauncherVisualization", DummyVisualizationLauncher
    )
    monkeypatch.setattr("manager.manager.manager.Server", DummyServer)
    monkeypatch.setattr("manager.manager.manager.FileWatchdog", DummyFileWatchdog)

    # Setup Manager with dummy consumer
    m = Manager(host="localhost", port=12345)
    m.consumer = DummyConsumer()
    # Move to 'connected' state first
    m.trigger("connect", event=None)
    return m


def setup_manager_to_visualization_ready(manager):
    """Move manager to visualization_ready state."""

    # Initial state should be 'connected'
    assert manager.state == "connected"

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

    # Trigger visualization ready state
    manager.trigger(
        "prepare_visualization",
        data={
            "type": "gazebo_rae",
            "file": "test_file",
        },
    )

    assert manager.state == "visualization_ready"


def test_visualization_ready_to_application_running_valid(manager, monkeypatch):
    """
    Test transitioning from 'visualization_ready' to 'application_running' state.

    This test verifies the state transitions in case of valid values.
    """
    setup_manager_to_visualization_ready(manager)

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


def test_on_run_application_missing_code(manager, monkeypatch):
    """Test running application with missing code file."""
    setup_manager_to_visualization_ready(manager)

    # Mock file system so code file is missing
    monkeypatch.setattr("os.path.isfile", lambda path: False)
    # Mock open for app.zip to avoid FileNotFoundError
    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/workspace/code/app.zip":
            import io

            return io.BytesIO()
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    # Mock other unimportant operations
    monkeypatch.setattr("os.listdir", lambda path: ["0", "1", "2"])
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: None)
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
    # Prep data
    data = {"type": "robotics-academy", "code": "data:base64,ZmFrZV9jb2Rl"}
    # Trigger run_application with missing code
    with pytest.raises(Exception, match="User code not found"):
        manager.trigger("run_application", data=data)
    assert manager.application_process is None
    # Ensure state is still visualization_ready
    assert manager.state == "visualization_ready"


def test_on_run_application_corrupt_zip(manager, monkeypatch):
    """Test running application with corrupt zip/base64."""
    setup_manager_to_visualization_ready(manager)

    # Mock file system so code dir exists
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("os.mkdir", lambda path: None)
    monkeypatch.setattr("os.listdir", lambda path: ["0", "1", "2"])
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    # Mock open for app.zip to avoid FileNotFoundError
    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/workspace/code/app.zip":
            import io

            return io.BytesIO()
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    # Simulate corrupt base64 decoding
    monkeypatch.setattr(
        "base64.b64decode", lambda s: (_ for _ in ()).throw(Exception("Corrupt base64"))
    )
    # Mock other unimportant operations
    monkeypatch.setattr(
        "zipfile.ZipFile",
        lambda *a, **k: type(
            "Zip",
            (),
            {"extractall": lambda self, path: None, "close": lambda self: None},
        )(),
    )
    monkeypatch.setattr(
        "manager.manager.manager.Manager.unpause_sim", lambda self: None
    )
    manager.linter.evaluate_code = lambda code, ros_version: ""
    data = {"type": "robotics-academy", "code": "data:base64,ZmFrZV9jb2Rl"}
    with pytest.raises(Exception, match="Corrupt base64"):
        manager.trigger("run_application", data=data)
    assert manager.application_process is None
    assert manager.state == "visualization_ready"
