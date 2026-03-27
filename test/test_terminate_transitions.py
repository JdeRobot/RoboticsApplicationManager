"""Tests for resume and pause transitions in the Manager."""

import pytest
from transitions import MachineError
from conftest import DummyServer
from test_utils import setup_manager_to_application_running
from test_utils import setup_manager_to_world_ready
from test_utils import setup_manager_to_tools_ready


class DummyProc:
    """Dummy process class for testing suspend and resume methods."""

    def suspend(self):
        """Simulate suspending the process."""
        pass

    def resume(self):
        """Simulate resuming the process."""
        pass


class DummyToolsLauncher:
    """Dummy class for testing visualization launching."""

    def launch(self):
        """Simulate launching the visualization."""
        pass

    def stop(self):
        """Simulate stopping the visualization."""
        pass

    def terminate(self):
        """Simulate terminating the visualization."""
        pass


def test_terminate_application_valid(manager, monkeypatch):
    """Test the valid terminate application transition in the Manager."""
    # Ensure the manager is in a state where it can terminate
    setup_manager_to_application_running(manager, monkeypatch)
    # Mock needed methods and attributes

    def dummy_stop_process_and_children(proc):
        pass

    monkeypatch.setattr(
        "robotics_application_manager.manager.manager.stop_process_and_children",
        dummy_stop_process_and_children,
    )
    manager.pause_sim = lambda: None
    manager.reset_sim = lambda: None

    # Trigger the terminate transition
    manager.trigger("terminate_application")
    # Check that the state has changed to 'visualization_ready'
    assert manager.state == "tools_ready"


def test_terminate_application_invalid_machine_error(manager, monkeypatch):
    """
    Test the valid terminate application transition in the Manager.

    Ensure that the transition raises an error when executed from an invalid state.
    """
    # Ensure the manager is in a state where it can terminate
    setup_manager_to_world_ready(manager, monkeypatch)
    # Mock needed methods and attributes

    def dummy_stop_process_and_children(proc):
        pass

    monkeypatch.setattr(
        "robotics_application_manager.manager.manager.stop_process_and_children",
        dummy_stop_process_and_children,
    )
    manager.pause_sim = lambda: None
    manager.reset_sim = lambda: None

    # Trigger the terminate transition
    with pytest.raises(MachineError):
        manager.trigger("terminate_application")
    # Check that the state has not changed
    assert manager.state == "world_ready"


def test_terminate_tools_valid(manager, monkeypatch):
    """Test the valid terminate visualization transition in the Manager."""
    # Ensure the manager is in a state where it can stop
    setup_manager_to_tools_ready(manager, monkeypatch)
    # Mock needed methods and attributes
    manager.visualization_launcher = DummyToolsLauncher()
    manager.terminate_harmonic_processes = lambda: None

    # Trigger the stop transition
    manager.trigger("terminate_tools")
    # Check that the state has changed to 'world_ready'
    assert manager.state == "world_ready"


def test_terminate_tools_invalid_machine_error(manager, monkeypatch):
    """
    Test the invalid terminate visualization transition in the Manager.

    Ensure that the transition raises an error when executed from an invalid state.
    """
    monkeypatch.setattr("robotics_application_manager.libs.server.Server", DummyServer)
    # Ensure the manager is in a state where it can stop
    setup_manager_to_application_running(manager, monkeypatch)

    # Trigger the stop transition
    with pytest.raises(MachineError):
        manager.trigger("terminate_tools")
    # Check that the state has not changed
    assert manager.state == "application_running"


def test_terminate_universe_valid(manager, monkeypatch):
    """Test the valid terminate_universe transition in the Manager."""
    # Ensure the manager is in a state where it can stop
    setup_manager_to_world_ready(manager, monkeypatch)
    # Mock needed methods and attributes
    manager.visualization_launcher = DummyToolsLauncher()
    manager.terminate_harmonic_processes = lambda: None

    # Trigger the stop transition
    manager.trigger("terminate_universe")
    # Check that the state has changed to 'connected'
    assert manager.state == "connected"


def test_terminate_universe_invalid_machine_error(manager, monkeypatch):
    """
    Test the invalid terminate_universe transition in the Manager.

    Ensure that the transition raises an error when executed from an invalid state.
    """
    # Ensure the manager is in a state where it can stop
    setup_manager_to_application_running(manager, monkeypatch)

    # Trigger the stop transition
    with pytest.raises(MachineError):
        manager.trigger("terminate_universe")
    # Check that the state has not changed
    assert manager.state == "application_running"
