"""Utility functions to transition the Manager to a specific state for testing."""

import pytest
from manager.manager.manager import Manager

# Patch Server and FileWatchdog to avoid starting real servers


class DummyServer:
    def __init__(self, host, port, loglevel):
        self.host = host
        self.port = port
        self.loglevel = loglevel

    def set_fn_new_client(self, fn):
        pass

    def set_fn_client_left(self, fn):
        pass

    def set_fn_message_received(self, fn):
        pass

    def deny_new_connections(self):
        pass

    def allow_new_connections(self):
        pass

    def send_message(self, client, message):
        pass

    def run_forever(self, threaded=True):
        pass

    def shutdown_gracefully(self):
        pass


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

    def stop(self):
        """Simulate consumer stopping."""
        pass


@pytest.fixture
def manager(monkeypatch):
    """Fixture to provide a Manager instance with patched dependencies for testing."""

    monkeypatch.setattr("manager.comms.websocket_server.WebsocketServer", DummyServer)

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

    def dummy_run(self, start_pose=None):
        print("run around")

    monkeypatch.setattr(
        "manager.manager.launcher.launcher_robot.LauncherRobot.run", dummy_run
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

    class DummyFileWatchdog:
        def __init__(self, path, update_callback):
            self.path = path
            self.update_callback = update_callback
            self.started = False

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

    class DummyToolsLauncher:
        def __init__(self, *args, **kwargs):
            self.launchers = []

        def run(self, consumer):
            # Simulate running the tools launcher
            return

        def terminate(self):
            pass

    monkeypatch.setattr("manager.manager.manager.LauncherTools", DummyToolsLauncher)
    # Deprecated
    # monkeypatch.setattr("manager.manager.manager.Server", DummyServer)
    # monkeypatch.setattr("manager.manager.manager.FileWatchdog", DummyFileWatchdog)

    # Setup Manager with dummy consumer
    m = Manager(host="localhost", port=12345)
    m.consumer = DummyConsumer()
    return m
