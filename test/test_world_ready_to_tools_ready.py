"""Tests for transitioning Manager from 'connected' to 'world_ready' state."""

import pytest
from test_utils import setup_manager_to_world_ready


def test_on_prepare_tools_valid(manager, monkeypatch):
    """
    Test the transition from 'world_ready' to 'visualization_ready' state.

    Tests the preparation of the visualization state by triggering the
    prepare_tools event with valid values.
    """
    # Ensure the manager is in 'world_ready' state
    setup_manager_to_world_ready(manager, monkeypatch)
    # Trigger the prepare_tools event
    manager.trigger(
        "prepare_tools",
        data={
            "tools": ["tool1", "tool2"],
            "config": {"param1": "value1", "param2": "value2"},
        },
    )

    # Check if the state has transitioned to 'visualization_ready'
    assert manager.state == "tools_ready"

    print(manager.consumer.last_message)

    # Verify that the correct message was sent
    assert manager.consumer.last_message[0][0]["state"] == "tools_ready"


def test_on_prepare_tools_invalid(manager, monkeypatch):
    """
    Test the transition from 'world_ready' to 'visualization_ready' state.

    Tests that the prepare_tools event does not change the state
    when invalid values are provided.
    """
    # Ensure the manager is in 'world_ready' state
    setup_manager_to_world_ready(manager, monkeypatch)
    # Trigger the prepare_tools event with invalid data
    with pytest.raises(KeyError):
        # This should raise an error due to missing 'type' in data
        manager.trigger(
            "prepare_tools",
            data={
                "file": "test_file",
            },
        )

    # Check if the state remains 'world_ready'
    assert manager.state == "world_ready"
