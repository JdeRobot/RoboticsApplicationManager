import websocket
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from robotics_application_manager.comms.consumer_message import ManagerConsumerMessage


class ConnectCmd(ManagerConsumerMessage):
    id: str = "1"
    command: str = "connect"


class LaunchWorldCmd(ManagerConsumerMessage):
    id: str = "2"
    command: str = "launch_world"
    data: dict = {
        "world": {
            "type": "gz",
            "launch_file_path": "/opt/jderobot/Launchers/simple_circuit.launch.py",
        },
        "robot": {
            "type": None,
        },
    }


class LaunchPrepareTools(ManagerConsumerMessage):
    id: str = "3"
    command: str = "prepare_tools"
    data: dict = {
        "tools": ["console", "simulator"],
        "config": {},
    }


websocket.enableTrace(True)
ws = websocket.create_connection("ws://localhost:7163")

ws.send(ConnectCmd().json())
ws.send(LaunchWorldCmd().json())
ws.send(LaunchPrepareTools().json())


while True:
    try:
        user_input = input()  # Ctrl+D to exit
    except EOFError:
        exit()


# Open VNC: http://127.0.0.1:6080/vnc.html
