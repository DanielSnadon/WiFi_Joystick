import asyncio
import unittest

from aiohttp import WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer

from server import GamepadServer, create_app


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.receiver = GamepadServer("secret", mock=True)
        self.client = TestClient(TestServer(create_app(self.receiver)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_page_auth_and_controller_state(self):
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("Wi‑Fi Gamepad", await response.text())

        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect("/ws?token=wrong")

        ws = await self.client.ws_connect("/ws?token=secret")
        self.assertEqual((await ws.receive_json())["type"], "ready")
        await ws.send_json({"type": "hello", "deviceId": "tablet-1", "name": "Mi Pad", "preferredSlot": 1, "inputType": "touch"})
        assigned = await ws.receive_json()
        self.assertEqual(assigned["slot"], 1)
        devices = await ws.receive_json()
        self.assertEqual(devices["type"], "devices")
        self.assertEqual(devices["devices"][0]["inputType"], "touch")
        await ws.send_json({"type": "input_type", "inputType": "desktop"})
        devices = await ws.receive_json()
        self.assertEqual(devices["devices"][0]["inputType"], "desktop")
        await ws.send_json({"type": "state", "state": {"lx": 0.5, "buttons": ["A"]}})
        await asyncio.sleep(0.02)
        self.assertEqual(self.receiver.pads[0].state.lx, 0.5)
        self.assertEqual(self.receiver.pads[0].state.buttons, {"A"})
        await ws.close()
        self.assertEqual(self.receiver.pads[0].state.buttons, set())

    async def test_multiple_devices_use_independent_player_slots(self):
        first = await self.client.ws_connect("/ws?token=secret")
        await first.receive_json()
        await first.send_json({"type": "hello", "deviceId": "one", "name": "Tablet", "preferredSlot": 2})
        self.assertEqual((await first.receive_json())["slot"], 2)
        await first.receive_json()

        second = await self.client.ws_connect("/ws?token=secret")
        await second.receive_json()
        await second.send_json({"type": "hello", "deviceId": "two", "name": "Computer", "preferredSlot": 3, "inputType": "desktop"})
        self.assertEqual((await second.receive_json())["slot"], 3)
        devices = await second.receive_json()
        self.assertEqual({item["slot"] for item in devices["devices"]}, {2, 3})
        self.assertEqual(next(item for item in devices["devices"] if item["slot"] == 3)["inputType"], "desktop")
        await first.receive_json()

        await first.send_json({"type": "state", "state": {"buttons": ["A"]}})
        await second.send_json({"type": "state", "state": {"buttons": ["B"]}})
        await asyncio.sleep(0.02)
        self.assertEqual(self.receiver.pads[0].state.buttons, set())
        self.assertEqual(self.receiver.pads[1].state.buttons, {"A"})
        self.assertEqual(self.receiver.pads[2].state.buttons, {"B"})

        await second.send_json({"type": "set_slot", "slot": 2})
        error = await second.receive_json()
        self.assertEqual(error["type"], "error")
        await first.close()
        await second.close()


if __name__ == "__main__":
    unittest.main()
