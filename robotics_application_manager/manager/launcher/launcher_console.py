from .launcher_interface import ILauncher
from robotics_application_manager import LogManager
from typing import List, Any
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosedOK
from robotics_application_manager import LogManager
import json
import asyncio
import asyncssh
import subprocess

async def ssh_shell(
    ws,
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
              try:
                async for raw in ws:
                  if type(raw) == str:
                    process.stdin.write(raw)
                    await process.stdin.drain()
                  elif type(raw) == bytes:
                      data = raw
                      msg = json.loads(data.decode("utf-8"))
                      if "resize" in msg:
                          cols = int(msg["resize"].get("cols", init_cols))
                          rows = int(msg["resize"].get("rows", init_rows))
                          process.change_terminal_size(cols, rows)
                  # elif raw["type"] == "websocket.disconnect":
                  #     raise UserWarning("ws-to-ssh ws disconnect")
              except:
                raise UserWarning("ws-to-ssh ws disconnect")

            async def ssh_to_ws():
                while True:
                    data = await process.stdout.read(4096)
                    if not data:
                        raise UserWarning("ssh-to-ws process close")
                    await ws.send(data)

            async with asyncio.TaskGroup() as tg:
                tg.create_task(ws_to_ssh())
                tg.create_task(ssh_to_ws())



class LauncherConsole:
    internal_port: int
    external_port: int
    running: bool = False
    acceptsMsgs: bool = False

    def __init__(self, type, module, internal_port, external_port):
        self.internal_port = internal_port
        self.external_port = external_port
        self.client = None

    def __await__(self):
        return self.create().__await__()

    async def create(self):
        self.server = await serve(self.manage_conection, "127.0.0.1", self.external_port, start_serving=False)
        return self

    async def run(self, config_file, callback):
        LogManager.logger.info(f"Console started")
        await self.server.start_serving()
        self.running = True

    async def manage_conection(self, websocket):
        if self.client is not None:
          await websocket.close()
          return

        try:
            self.client = websocket # Register client
            LogManager.logger.info(f"Client connected: {self.client}")
            # init_cols = int(websocket.query_params.get("cols") or 80)
            # init_rows = int(websocket.query_params.get("rows") or 24)
            user = "root"
            await ssh_shell(websocket, user, self.internal_port, "jderobot")
        except ConnectionClosedOK as e:
            pass
        finally:
            LogManager.logger.info("Connection with client closed")
            self.client = None

    def pause(self):
        pass

    def unpause(self):
        pass

    def reset(self, robot_entities=[]):
        pass

    def is_running(self):
        return self.running

    async def terminate(self):
        self.server.close()
        await self.server.wait_closed()
        self.running = False

    def died(self):
        pass

    async def from_config(cls, config):
        obj = await cls(**config)
        return obj
