"""Tests for transitioning Manager from 'connected' to 'world_ready' state."""

import pytest

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


def test_on_prepare_visualization_valid(manager):
    """
    Test the transition from 'world_ready' to 'visualization_ready' state.

    Tests the preparation of the visualization state by triggering the
    prepare_visualization event with valid values.
    """
    # Ensure the manager is in 'world_ready' state
    manager.state = "world_ready"
    # Trigger the prepare_visualization event
    manager.trigger(
        "prepare_visualization",
        data={
            "type": "gazebo_rae",
            "file": "test_file",
        },
    )

    # Check if the state has transitioned to 'visualization_ready'
    assert manager.state == "visualization_ready"

    print(manager.consumer.last_message)

    # Verify that the correct message was sent
    assert manager.consumer.last_message[0][0]["state"] == "visualization_ready"


def test_on_prepare_visualization_invalid(manager):
    """
    Test the transition from 'world_ready' to 'visualization_ready' state.

    Tests that the prepare_visualization event does not change the state
    when invalid values are provided.
    """
    # Ensure the manager is in 'world_ready' state
    manager.state = "world_ready"
    # Trigger the prepare_visualization event with invalid data
    with pytest.raises(KeyError):
        # This should raise an error due to missing 'type' in data
        manager.trigger(
            "prepare_visualization",
            data={
                "file": "test_file",
            },
        )

    # Check if the state remains 'world_ready'
    assert manager.state == "world_ready"
