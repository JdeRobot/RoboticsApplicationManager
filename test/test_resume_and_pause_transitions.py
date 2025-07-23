"""Tests for resume and pause transitions in the Manager."""

import pytest
from transitions import MachineError
from test_utils import setup_manager_to_application_running
from test_utils import setup_manager_to_tools_ready


class DummyProc:
    """Dummy process class for testing suspend and resume methods."""

    def suspend(self):
        """Simulate suspending the process."""
        pass

    def resume(self):
        """Simulate resuming the process."""
        pass


def test_pause_transition_valid(manager, monkeypatch):
    """Test the valid pause transition in the Manager."""
    # Ensure the manager is in a state where it can pause
    setup_manager_to_application_running(manager, monkeypatch)
    # Mock needed methods and attributes
    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())

    manager.pause_sim = lambda: None

    # Trigger the pause transition
    manager.trigger("pause")
    # Check that the state has changed to 'paused'
    assert manager.state == "paused"
    # Verify that the consumer received the correct message
    assert manager.consumer.last_message[0][0]["state"] == "paused"


def test_pause_transition_invalid_machine_error(manager, monkeypatch):
    """Test the invalid pause transition in the Manager."""
    # Ensure the manager is in a state where it can pause
    setup_manager_to_tools_ready(manager, monkeypatch)

    # Mock needed methods and attributes
    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())

    # Trigger the pause transition
    with pytest.raises(MachineError):
        manager.trigger("pause")
    # Check that the state has changed to 'paused'
    assert manager.state == "tools_ready"


def test_resume_transition_valid(manager, monkeypatch):
    """Test the valid resume transition in the Manager."""
    # Ensure the manager is in a paused state
    setup_manager_to_application_running(manager, monkeypatch)

    # Mock needed methods and attributes
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
    assert manager.consumer.last_message[0][0]["state"] == "application_running"


def test_resume_transition_invalid(manager, monkeypatch):
    """Test the invalid resume transition in the Manager."""
    # Ensure the manager is in a state where it can resume
    setup_manager_to_application_running(manager, monkeypatch)

    # Mock needed methods and attributes
    monkeypatch.setattr("psutil.Process", lambda pid: DummyProc())

    # Trigger the resume transition
    with pytest.raises(MachineError):
        manager.trigger("resume")
    # Check that the state has not changed
    assert manager.state == "application_running"
