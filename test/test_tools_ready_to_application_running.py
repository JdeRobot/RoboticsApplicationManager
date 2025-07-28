"""Tests for transitioning Manager from 'connected' to 'world_ready' state."""

import io
import pytest
import builtins
from test_utils import setup_manager_to_tools_ready

valid_app_data = {
    "entrypoint": "main.py",
    "linter": "pylint",
    "code": "data:base64,ZmFrZV9jb2Rl",
}


def test_tools_ready_to_application_running_valid(manager, monkeypatch):
    """
    Test transitioning from 'tools_ready' to 'application_running' state.

    This test verifies the state transitions in case of valid values.
    """
    setup_manager_to_tools_ready(manager, monkeypatch)

    class DummyProc:
        def __init__(self):
            self.pid = 123

        def kill(self):
            pass

        def suspend(self):
            pass

    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/workspace/code/app.zip":
            if "w" in mode:
                return io.BytesIO()
            elif "r" in mode:
                return io.BytesIO(b"fake zip content")
        return original_open(file, mode, *args, **kwargs)

    # Mock file system and subprocess operations
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.listdir", lambda path: ["0", "1", "2"])
    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: DummyProc())
    monkeypatch.setattr("os.mkdir", lambda path: None)
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    monkeypatch.setattr(
        "zipfile.ZipFile",
        lambda *a, **k: type(
            "Zip",
            (),
            {"extractall": lambda self, path: None, "close": lambda self: None},
        )(),
    )
    monkeypatch.setattr("base64.b64decode", lambda s: b"print('hello')")
    monkeypatch.setattr(
        "manager.manager.manager.Manager.unpause_sim", lambda self: None
    )
    # Mock linter to return no errors
    manager.linter.evaluate_code = lambda code, ros_version: ""
    # Trigger application running state
    manager.trigger(
        "run_application",
        data=valid_app_data,
    )
    # Assert state is now application_running
    assert manager.state == "application_running"


def test_on_run_application_missing_code(manager, monkeypatch):
    """Test running application with missing code file."""
    setup_manager_to_tools_ready(manager, monkeypatch)

    # Mock file system so code file is missing
    monkeypatch.setattr("os.path.isfile", lambda path: False)
    # Mock open for app.zip to avoid FileNotFoundError
    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/workspace/code/app.zip":
            import io

            return io.BytesIO()
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    # Mock other unimportant operations
    monkeypatch.setattr("os.listdir", lambda path: ["0", "1", "2"])
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: None)
    monkeypatch.setattr("os.mkdir", lambda path: None)
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    monkeypatch.setattr(
        "zipfile.ZipFile",
        lambda *a, **k: type(
            "Zip",
            (),
            {"extractall": lambda self, path: None, "close": lambda self: None},
        )(),
    )
    monkeypatch.setattr("base64.b64decode", lambda s: b"print('hello')")
    monkeypatch.setattr(
        "manager.manager.manager.Manager.unpause_sim", lambda self: None
    )
    # Mock linter to return no errors
    manager.linter.evaluate_code = lambda code, ros_version: ""
    # Prep data
    data = valid_app_data
    # Trigger run_application with missing code
    with pytest.raises(Exception, match="User code not found"):
        manager.trigger("run_application", data=data)
    assert manager.application_process is None
    # Ensure state is still tools_ready
    assert manager.state == "tools_ready"


def test_on_run_application_corrupt_zip(manager, monkeypatch):
    """Test running application with corrupt zip/base64."""
    setup_manager_to_tools_ready(manager, monkeypatch)

    # Mock file system so code dir exists
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr("os.mkdir", lambda path: None)
    monkeypatch.setattr("os.listdir", lambda path: ["0", "1", "2"])
    monkeypatch.setattr("shutil.rmtree", lambda path: None)
    # Mock open for app.zip to avoid FileNotFoundError
    original_open = builtins.open

    def fake_open(file, mode="r", *args, **kwargs):
        if file == "/workspace/code/app.zip":
            import io

            return io.BytesIO()
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    # Simulate corrupt base64 decoding
    monkeypatch.setattr(
        "base64.b64decode", lambda s: (_ for _ in ()).throw(Exception("Corrupt base64"))
    )
    # Mock other unimportant operations
    monkeypatch.setattr(
        "zipfile.ZipFile",
        lambda *a, **k: type(
            "Zip",
            (),
            {"extractall": lambda self, path: None, "close": lambda self: None},
        )(),
    )
    monkeypatch.setattr(
        "manager.manager.manager.Manager.unpause_sim", lambda self: None
    )
    manager.linter.evaluate_code = lambda code, ros_version: ""
    data = valid_app_data
    with pytest.raises(Exception):
        manager.trigger("run_application", data=data)
    assert manager.application_process is None
    assert manager.state == "tools_ready"
