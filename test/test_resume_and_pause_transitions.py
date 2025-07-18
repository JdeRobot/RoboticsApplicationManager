"""Tests for resume and pause transitions in the Manager."""

import pytest
from transitions import MachineError
import utils as test_utils
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
    return m


def test_pause_transition_valid(manager, monkeypatch):
    """Test the valid pause transition in the Manager."""
    # Ensure the manager is in a state where it can pause
    test_utils.setup_manager_to_application_running(manager, monkeypatch)

    # Mock needed methods and attributes
    class DummyProc:
        def suspend(self):
            pass

    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())

    manager.pause_sim = lambda: None

    # Trigger the pause transition
    manager.trigger("pause")
    # Check that the state has changed to 'paused'
    assert manager.state == "paused"
    # Verify that the consumer received the correct message
    assert manager.consumer.last_message[0][0]['state'] == "paused"


def test_pause_transition_invalid_machine_error(manager, monkeypatch):
    """Test the invalid pause transition in the Manager."""
    # Ensure the manager is in a state where it can pause
    test_utils.setup_manager_to_visualization_ready(manager, monkeypatch)

    # Mock needed methods and attributes
    class DummyProc:
        def suspend(self):
            pass

    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())

    # Trigger the pause transition
    with pytest.raises(MachineError):
        manager.trigger("pause")
    # Check that the state has changed to 'paused'
    assert manager.state == "visualization_ready"


def test_resume_transition_valid(manager, monkeypatch):
    """Test the valid resume transition in the Manager."""
    # Ensure the manager is in a paused state
    test_utils.setup_manager_to_application_running(manager, monkeypatch)

    # Mock needed methods and attributes
    class DummyProc:
        def suspend(self):
            pass

        def resume(self):
            pass

    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())
    manager.pause_sim = lambda: None

    # Move to 'paused' state first
    manager.trigger("pause")
    assert manager.state == "paused"

    # Trigger the resume transition
    manager.trigger("resume")
    # Check that the state has changed to 'application_running'
    assert manager.state == "application_running"
    # Verify that the consumer received the correct message
    assert manager.consumer.last_message[0][0]['state'] == "application_running"


def test_resume_transition_invalid(manager, monkeypatch):
    """Test the invalid resume transition in the Manager."""
    # Ensure the manager is in a state where it can resume
    test_utils.setup_manager_to_application_running(manager, monkeypatch)

    # Mock needed methods and attributes
    class DummyProc:
        def resume(self):
            pass

    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())

    # Trigger the resume transition
    with pytest.raises(MachineError):
        manager.trigger("resume")
    # Check that the state has not changed
    assert manager.state == "application_running"
