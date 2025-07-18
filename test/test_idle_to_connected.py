"""Tests for transitioning Manager from 'idle' to 'connected' state."""

import pytest


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
