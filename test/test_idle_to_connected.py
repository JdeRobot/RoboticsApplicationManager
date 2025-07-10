"""Tests for transitioning Manager from 'idle' to 'connected' state."""

import pytest

from manager.manager.manager import Manager


class DummyConsumer:
    """A dummy consumer to capture messages sent by the Manager."""

    def __init__(self):
        """Initialize the DummyConsumer with empty message storage."""
        self.messages = []
        self.last_message = None

    def send_message(self, *args, **kwargs):
        """Capture the message sent by the Manager."""
        self.messages.append((args, kwargs))
        # Store the last message for verification
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

    # Setup Manager with dummy consumer
    m = Manager(host="localhost", port=12345)
    m.consumer = DummyConsumer()
    return m


def test_idle_to_connected(manager):
    """Test transitioning Manager from 'idle' to 'connected' state."""
    # Initial state should be 'idle'
    assert manager.state == "idle"
    # Simulate the 'connect' event
    manager.trigger("connect", event=None)
    # State should now be 'connected'
    assert manager.state == "connected"
    # Check that the consumer received the expected message
    msgs = manager.consumer.messages
    on_connect_msg = msgs[0][0]
    state_change_msg = msgs[1]
    # print(msgs)
    # Verify the first message (on connect)
    assert on_connect_msg[0]["robotics_backend_version"] == b"test_image_tag"
    assert on_connect_msg[0]["ros_version"] == b"humble"
    assert on_connect_msg[0]["gpu_avaliable"] == "OFF"

    # Verify the state change message
    assert state_change_msg[0][0]["state"] == "connected"
    assert state_change_msg[1]["command"] == "state-changed"


def test_idle_to_connected_with_exception(manager):
    """Test transitioning Manager from 'idle' to 'connected' state with an exception."""
    # Simulate an exception during the connection process
    manager.consumer.send_message = lambda *args, **kwargs: (
        1 / 0  # This will raise a ZeroDivisionError
    )

    with pytest.raises(ZeroDivisionError):
        manager.trigger("connect", event=None)

    # State should still be 'idle' after the exception
    assert manager.state == "idle"

    # Check that no messages were sent to the consumer
    assert not manager.consumer.messages
