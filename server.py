from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from aiohttp import WSMsgType, web

from controller import PadState, create_gamepad


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
STALE_AFTER_SECONDS = 0.75
MAX_PLAYERS = 4


@dataclass
class ClientInfo:
    device_id: str
    name: str
    slot: int
    last_update: float
    input_type: str = "touch"
    released: bool = False


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


class GamepadServer:
    def __init__(self, token: str, mock: bool = False) -> None:
        self.token = token
        self.mock = mock
        self.pads = [create_gamepad(mock)]
        self.clients: dict[web.WebSocketResponse, ClientInfo] = {}

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_ROOT / "index.html")

    async def websocket(self, request: web.Request) -> web.StreamResponse:
        if request.query.get("token") != self.token:
            raise web.HTTPUnauthorized(text="Неверный ключ подключения")

        ws = web.WebSocketResponse(heartbeat=15, max_msg_size=8_192)
        await ws.prepare(request)

        await ws.send_json({"type": "ready", "maxPlayers": MAX_PLAYERS})

        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    continue
                try:
                    payload = json.loads(message.data)
                except (json.JSONDecodeError, TypeError):
                    continue
                message_type = payload.get("type")
                if message_type == "hello":
                    await self.register_client(ws, payload)
                elif message_type == "state" and isinstance(payload.get("state"), dict):
                    info = self.clients.get(ws)
                    if info:
                        self.pads[info.slot - 1].apply(PadState.from_message(payload["state"]))
                        info.last_update = time.monotonic()
                        info.released = False
                elif message_type == "set_slot":
                    await self.set_slot(ws, payload.get("slot"))
                elif message_type == "rename":
                    await self.rename_client(ws, payload.get("name"))
                elif message_type == "input_type":
                    await self.set_input_type(ws, payload.get("inputType"))
        finally:
            info = self.clients.pop(ws, None)
            if info:
                self.pads[info.slot - 1].reset()
                await self.broadcast_devices()
        return ws

    def ensure_pads(self, count: int) -> None:
        while len(self.pads) < count:
            self.pads.append(create_gamepad(self.mock))

    def slot_in_use(self, slot: int, except_ws: web.WebSocketResponse | None = None) -> bool:
        return any(ws is not except_ws and info.slot == slot for ws, info in self.clients.items())

    def first_free_slot(self) -> int | None:
        return next((slot for slot in range(1, MAX_PLAYERS + 1) if not self.slot_in_use(slot)), None)

    async def register_client(self, ws: web.WebSocketResponse, payload: dict) -> None:
        raw_id = str(payload.get("deviceId", ""))[:64]
        device_id = "".join(char for char in raw_id if char.isalnum() or char in "-_") or secrets.token_hex(8)
        name = self.clean_name(payload.get("name"))
        requested = payload.get("preferredSlot")
        requested = requested if isinstance(requested, int) and 1 <= requested <= MAX_PLAYERS else None

        previous_slot = None
        for old_ws, old_info in list(self.clients.items()):
            if old_info.device_id == device_id and old_ws is not ws:
                previous_slot = old_info.slot
                self.clients.pop(old_ws, None)
                self.pads[old_info.slot - 1].reset()
                await old_ws.close(code=4002, message=b"Device reconnected")

        preferred = requested or previous_slot
        slot = preferred if preferred and not self.slot_in_use(preferred) else self.first_free_slot()
        if slot is None:
            await ws.send_json({"type": "error", "message": "Все четыре игровых слота заняты"})
            await ws.close(code=4003, message=b"No free player slots")
            return

        try:
            self.ensure_pads(slot)
        except RuntimeError as error:
            await ws.send_json({"type": "error", "message": str(error)})
            return
        input_type = "desktop" if payload.get("inputType") == "desktop" else "touch"
        self.clients[ws] = ClientInfo(device_id, name, slot, time.monotonic(), input_type)
        self.pads[slot - 1].reset()
        await ws.send_json({"type": "assigned", "slot": slot, "deviceId": device_id})
        await self.broadcast_devices()

    async def set_slot(self, ws: web.WebSocketResponse, raw_slot) -> None:
        info = self.clients.get(ws)
        if not info:
            return
        try:
            slot = int(raw_slot)
        except (TypeError, ValueError):
            return
        if not 1 <= slot <= MAX_PLAYERS:
            return
        if self.slot_in_use(slot, except_ws=ws):
            await ws.send_json({"type": "error", "message": f"Слот P{slot} уже занят"})
            await self.broadcast_devices()
            return
        try:
            self.ensure_pads(slot)
        except RuntimeError as error:
            await ws.send_json({"type": "error", "message": str(error)})
            return
        self.pads[info.slot - 1].reset()
        info.slot = slot
        info.last_update = time.monotonic()
        info.released = False
        self.pads[slot - 1].reset()
        await ws.send_json({"type": "assigned", "slot": slot, "deviceId": info.device_id})
        await self.broadcast_devices()

    async def rename_client(self, ws: web.WebSocketResponse, raw_name) -> None:
        info = self.clients.get(ws)
        if not info:
            return
        info.name = self.clean_name(raw_name)
        await self.broadcast_devices()

    async def set_input_type(self, ws: web.WebSocketResponse, raw_input_type) -> None:
        info = self.clients.get(ws)
        if not info:
            return
        info.input_type = "desktop" if raw_input_type == "desktop" else "touch"
        await self.broadcast_devices()

    @staticmethod
    def clean_name(raw_name) -> str:
        name = " ".join(str(raw_name or "Планшет").strip().split())
        return name[:24] or "Планшет"

    async def broadcast_devices(self) -> None:
        devices = [
            {"deviceId": info.device_id, "name": info.name, "slot": info.slot, "inputType": info.input_type}
            for info in sorted(self.clients.values(), key=lambda current: current.slot)
        ]
        message = {"type": "devices", "devices": devices, "padCount": len(self.pads)}
        for client in list(self.clients):
            if not client.closed:
                try:
                    await client.send_json(message)
                except (ConnectionError, RuntimeError):
                    pass

    async def watchdog(self, _app: web.Application):
        async def check() -> None:
            while True:
                await asyncio.sleep(0.2)
                now = time.monotonic()
                for info in list(self.clients.values()):
                    if now - info.last_update > STALE_AFTER_SECONDS and not info.released:
                        self.pads[info.slot - 1].reset()
                        info.released = True

        task = asyncio.create_task(check())
        yield
        task.cancel()
        for pad in self.pads:
            pad.reset()


def create_app(server: GamepadServer) -> web.Application:
    app = web.Application()
    app.router.add_get("/", server.index)
    app.router.add_get("/ws", server.websocket)
    app.router.add_static("/assets", WEB_ROOT, show_index=False)
    app.cleanup_ctx.append(server.watchdog)
    return app


def create_qr(url: str, image_path: Path) -> bool:
    try:
        import qrcode
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_Q,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr.make_image(fill_color="#07100b", back_color="#ffffff").convert("RGB").save(image_path)
        return True
    except Exception:
        return False


def print_qr(url: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Wi-Fi Gamepad receiver")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--mock", action="store_true", help="Run without a virtual controller")
    parser.add_argument("--no-host-panel", action="store_true", help="Do not start the native host input panel")
    args = parser.parse_args()

    if sys.platform != "win32" and not args.mock:
        print("Эта сборка создаёт виртуальный геймпад только на Windows. Для проверки используйте --mock.")
        return 1

    token = secrets.token_urlsafe(12)
    network_url = f"http://{local_ip()}:{args.port}/?token={token}"
    qr_path = Path(tempfile.gettempdir()) / f"wifi-gamepad-{token[:8]}.png"
    qr_ready = create_qr(network_url, qr_path)
    print("\nWI-FI GAMEPAD")
    print("1. Оставьте это окно открытым.")
    print("2. Для клавиатуры и мыши используйте отдельную панель хоста.")
    print("3. На другом компьютере или планшете в той же Wi-Fi сети откройте:\n")
    print(network_url, "\n")
    print_qr(network_url)
    print("\nДля остановки нажмите Ctrl+C.\n")

    panel_process = None
    if sys.platform == "win32" and not args.mock and not args.no_host_panel:
        try:
            panel_process = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "host_panel.py"),
                    "--token", token,
                    "--port", str(args.port),
                    "--url", network_url,
                    *(["--qr", str(qr_path)] if qr_ready else []),
                ],
                cwd=ROOT,
            )
        except OSError as error:
            print(f"ПРЕДУПРЕЖДЕНИЕ: не удалось открыть панель хоста: {error}")

    try:
        web.run_app(create_app(GamepadServer(token, args.mock)), host=args.host, port=args.port, print=None)
    except RuntimeError as error:
        print(f"\nОШИБКА: {error}\n")
        return 1
    finally:
        if panel_process and panel_process.poll() is None:
            panel_process.terminate()
        if qr_ready:
            qr_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
