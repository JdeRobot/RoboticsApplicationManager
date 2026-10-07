from fastapi import APIRouter
from fastapi.websockets import WebSocket, WebSocketDisconnect, WebSocketState
import json
import os
import asyncio
import asyncssh
import subprocess

router = APIRouter(
    tags=["ssh"],
    responses={404: {"description": "Not found"}},
)


@router.websocket("/console")
async def terminal_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        init_cols = int(websocket.query_params.get("cols") or 80)
        init_rows = int(websocket.query_params.get("rows") or 24)
        user = "root"
        await ssh_shell(
            websocket, user, 8081, "jderobot", init_cols, init_rows, setting.val
        )
    except Exception as e:
        pass

    if websocket.client_state != WebSocketState.DISCONNECTED:
        await websocket.close()


async def ssh_shell(
    ws: WebSocket,
    user: str,
    port: int,
    passwd: str,
    init_cols: int = 80,
    init_rows: int = 24,
    workspace: str = "/",
):
    subprocess.run(["/usr/sbin/sshd"])
    async with asyncssh.connect(
        "localhost", port=port, username=user, password=passwd, known_hosts=None
    ) as conn:
        async with conn.create_process(
            term_type="xterm-color",
            term_size=(init_cols, init_rows),
            stderr=asyncssh.STDOUT,
        ) as process:
            process.stdin.write(f"cd {workspace};clear;\n")

            async def ws_to_ssh():
                while True:
                    raw = await ws.receive()
                    if raw.get("text"):
                        data = raw["text"]
                        process.stdin.write(data)
                        await process.stdin.drain()
                    elif raw.get("bytes"):
                        data = raw["bytes"]
                        msg = json.loads(data.decode("utf-8"))
                        if "resize" in msg:
                            cols = int(msg["resize"].get("cols", init_cols))
                            rows = int(msg["resize"].get("rows", init_rows))
                            process.change_terminal_size(cols, rows)
                    elif raw["type"] == "websocket.disconnect":
                        raise UserWarning("ws-to-ssh ws disconnect")

            async def ssh_to_ws():
                while True:
                    data = await process.stdout.read(4096)
                    if not data:
                        raise UserWarning("ssh-to-ws process close")
                    await ws.send_text(data)

            async with asyncio.TaskGroup() as tg:
                tg.create_task(ws_to_ssh())
                tg.create_task(ssh_to_ws())
