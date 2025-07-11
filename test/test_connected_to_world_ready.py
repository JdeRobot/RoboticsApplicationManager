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

    # Setup Manager with dummy consumer
    m = Manager(host="localhost", port=12345)
    m.consumer = DummyConsumer()
    # Move to 'connected' state first
    m.trigger("connect", event=None)
    return m


def test_connected_to_world_ready(manager):
    """Test transitioning Manager from 'connected' to 'world_ready' state."""
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

    # Check that the consumer received the expected state change message
    msgs = manager.consumer.messages
    state_change_msgs = [
        msg for msg in msgs if msg[1].get("command") == "state-changed"
    ]
    assert state_change_msgs
    assert state_change_msgs[-1][0][0]["state"] == "world_ready"


def test_launch_world_with_invalid_world_config(manager, monkeypatch):
    """Test that launching world with invalid world config logs error."""

    # Patch ConfigurationManager.validate to simulate a failed validation
    # but still return a dummy config
    class DummyConfig:
        def model_dump(self):
            return {}

    def fake_validate(cfg):
        # Simulate logging error, but return a dummy config to avoid UnboundLocalError
        return DummyConfig()

    monkeypatch.setattr(
        "manager.libs.launch_world_model.ConfigurationManager.validate", fake_validate
    )

    invalid_world_cfg = {"world": "bad_world"}  # missing launch_file_path
    event_data = {
        "world": invalid_world_cfg,
        "robot": {
            "world": None,
            "robot_config": {"name": "test_robot", "type": "simple"},
        },
    }
    manager.trigger("launch_world", data=event_data)
    # Assert that world_launcher is created but has no useful config
    assert manager.world_launcher is not None
    assert (
        getattr(manager.world_launcher, "world", None) is None
        or manager.world_launcher.world == ""
    )


def test_launch_world_with_invalid_robot_config(manager, monkeypatch):
    """Test that launching world with invalid robot config logs error."""

    # Patch ConfigurationManager.validate to simulate a failed validation
    # but still return a dummy config
    class DummyConfig:
        def model_dump(self):
            return {}

    def fake_validate(cfg):
        # Simulate logging error, but return a dummy config to avoid UnboundLocalError
        return DummyConfig()

    monkeypatch.setattr(
        "manager.libs.launch_world_model.ConfigurationManager.validate", fake_validate
    )

    valid_world_cfg = {
        "world": "test_world",
        "launch_file_path": "/path/to/launch_file.launch",
    }
    invalid_robot_cfg = {"name": "", "type": ""}  # Invalid robot config
    event_data = {
        "world": valid_world_cfg,
        "robot": {
            "world": valid_world_cfg,
            "robot_config": invalid_robot_cfg,
        },
    }

    with pytest.raises(ValueError):
        # This should raise an error due to invalid robot config
        manager.trigger("launch_world", data=event_data)

    # Assert that robot_launcher is not created
    assert manager.robot_launcher is None
    assert (
        getattr(manager.robot_launcher, "robot_config", None) is None
        or manager.robot_launcher.robot_config == {}
    )


def test_launch_world_with_no_world_config(manager):
    """Test that launching world with no world config does not raise an error."""
    # Initial state should be 'connected'
    assert manager.state == "connected"

    # Use ConfigurationModel for valid robot config
    from manager.libs.launch_world_model import ConfigurationModel

    valid_robot_cfg = ConfigurationModel(
        world="test_world",  # No world specified
        launch_file_path="/path/to/robot_launch_file.launch",
    ).model_dump()
    event_data = {
        "world": {
            "world": None,  # No world specified
            "launch_file_path": None,  # No launch file specified
        },  # No world specified
        "robot": valid_robot_cfg,
    }

    manager.trigger("launch_world", data=event_data)

    # State should now be 'world_ready'
    assert manager.state == "world_ready"
    assert manager.world_launcher is None


def test_launch_world_with_no_robot_config(manager):
    """Test that launching world with no robot config does not raise an error."""
    # Initial state should be 'connected'
    assert manager.state == "connected"

    # Use ConfigurationModel for valid world config
    from manager.libs.launch_world_model import ConfigurationModel

    valid_world_cfg = ConfigurationModel(
        world="test_world", launch_file_path="/path/to/launch_file.launch"
    ).model_dump()

    event_data = {
        "world": valid_world_cfg,
        "robot": {"world": None, "robot_config": None},  # No robot specified
    }
    manager.trigger("launch_world", data=event_data)

    # State should now be 'world_ready'
    assert manager.state == "world_ready"
    assert manager.robot_launcher is None
