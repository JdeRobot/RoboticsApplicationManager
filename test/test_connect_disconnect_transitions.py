"""Tests for transitioning Manager from 'idle' to 'connected' state."""

import pytest
from test_utils import setup_manager_to_world_ready
from test_utils import setup_manager_to_application_running


class DummyProc:
    """Dummy process class for testing suspend and resume methods."""

    def suspend(self):
        """Simulate suspending the process."""
        pass

    def resume(self):
        """Simulate resuming the process."""
        pass


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


def test_disconnect_valid(manager, monkeypatch):
    """Test the valid disconnect transition in the Manager."""
    # Ensure the manager is in a state where it can disconnect
    setup_manager_to_world_ready(manager, monkeypatch)

    # Mock needed methods and attributes
    manager.on_disconnect = lambda event: None

    # Trigger the disconnect transition
    manager.trigger("disconnect")

    # Check that the state has changed to 'idle'
    assert manager.state == "idle"


def test_disconnect_invalid_process(manager, monkeypatch):
    """
    Test the invalid disconnect transition in the Manager.

    Tests that the disconnect raises an Exception when the process
    cannot be disconnected properly.
    """
    # Ensure the manager is in a state where it can disconnect
    setup_manager_to_application_running(manager, monkeypatch)
    # Mock needed methods and attributes
    monkeypatch.setattr("os.execl", lambda *args: None)
    monkeypatch.setattr(
        "manager.manager.manager.stop_process_and_children",
        lambda proc: (_ for _ in ()).throw(Exception("Process cannot be stopped")),
    )
    manager.application_process = DummyProc()
    manager.terminate_harmonic_processes = lambda: None

    # Trigger the disconnect transition
    manager.trigger("disconnect")

    # Optional: can test that exception has been logged

    # Check that the state changed
    assert manager.state == "idle"
