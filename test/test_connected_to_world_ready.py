"""Tests for transitioning Manager from 'connected' to 'world_ready' state."""

import pytest
from robotics_application_manager.libs.launch_world_model import ConfigurationModel
from test_utils import setup_manager_to_connected
from robotics_application_manager.manager.launcher.launcher_robot import worlds

valid_world_cfg = ConfigurationModel(
    type=next(iter(worlds)), launch_file_path="/path/to/launch_file.launch"
).model_dump()

valid_robot_cfg = {
    "world": None,  # No robot specified
    # "type": next(iter(worlds)),  # Use the first world type
    "type": None,
    "start_pose": [0, 0, 0, 0, 0, 0],
    "launch_file_path": "/path/to/robot_launch_file.launch",
    "entity": "test",
    "extra_config": None,
}

invalid_world_cfg = {
    "world": "bad_world",
    "type": next(iter(worlds)),
    "launch_file_path": None,  # No launch file specified
}  # missing launch_file_path


def test_connected_to_world_ready(manager, monkeypatch):
    """Test transitioning Manager from 'connected' to 'world_ready' state."""
    # Initial state should be 'connected'
    setup_manager_to_connected(manager, monkeypatch)

    event_data = {"world": valid_world_cfg, "robot": valid_robot_cfg}
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


# def test_launch_world_with_invalid_world_config(manager, monkeypatch):
#     """Test that launching world with invalid world config logs error."""
#     # Initial state should be 'connected'
#     setup_manager_to_connected(manager, monkeypatch)

#     # Patch ConfigurationManager.validate to simulate a failed validation
#     # but still return a dummy config
#     class DummyConfig:
#         def model_dump(self):
#             return {}

#     def fake_validate(cfg):
#         # Simulate logging error, but return a dummy config to avoid UnboundLocalError
#         return DummyConfig()

#     def fake_prepare_custom_universe(cfg):
#         raise ValueError("Invalid world configuration")

#     monkeypatch.setattr(
#         "robotics_application_manager.libs.launch_world_model.ConfigurationManager.validate",
#         fake_validate,
#     )
#     manager.prepare_custom_universe = fake_prepare_custom_universe

#     event_data = {"world": invalid_world_cfg, "robot": valid_robot_cfg}

#     with pytest.raises(ValueError):
#         manager.trigger("launch_world", data=event_data)
#     # Assert that world_launcher is created but has no useful config
#     assert manager.world_launcher is not None
#     assert (
#         getattr(manager.world_launcher, "world", None) is None
#         or manager.world_launcher.world == ""
#     )


def test_launch_world_with_invalid_robot_config(manager, monkeypatch):
    """Test that launching world with invalid robot config logs error."""
    # Initial state should be 'connected'
    setup_manager_to_connected(manager, monkeypatch)

    # Patch ConfigurationManager.validate to simulate a failed validation
    # but still return a dummy config
    class DummyConfig:
        def model_dump(self):
            return {}

    def fake_validate(cfg):
        # Simulate logging error, but return a dummy config to avoid UnboundLocalError
        return DummyConfig()

    monkeypatch.setattr(
        "robotics_application_manager.libs.launch_world_model.ConfigurationManager.validate",
        fake_validate,
    )

    invalid_robot_cfg = {"name": "", "type": ""}  # Invalid robot config
    event_data = {
        "world": valid_world_cfg,
        "robot": invalid_robot_cfg,
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


def test_launch_world_with_no_world_config(manager, monkeypatch):
    """Test that launching world with no world config does not raise an error."""
    # Initial state should be 'connected'
    setup_manager_to_connected(manager, monkeypatch)

    event_data = {
        "world": {
            "world": None,  # No world specified
            "launch_file_path": None,  # No launch file specified
            "type": None,
        },  # No world specified
        "robot": valid_robot_cfg,
    }

    manager.trigger("launch_world", data=event_data)

    # State should now be 'world_ready'
    assert manager.state == "world_ready"
    assert manager.world_launcher is None


def test_launch_world_with_no_robot_config(manager, monkeypatch):
    """Test that launching world with no robot config does not raise an error."""
    # Initial state should be 'connected'
    setup_manager_to_connected(manager, monkeypatch)

    event_data = {
        "world": valid_world_cfg,
        "robot": {
            "world": None,
            "robot_config": None,
            "type": None,
        },  # No robot specified
    }
    manager.trigger("launch_world", data=event_data)

    # State should now be 'world_ready'
    assert manager.state == "world_ready"
    assert manager.robot_launcher is None
