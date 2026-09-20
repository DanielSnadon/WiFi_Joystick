from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


AXES = ("lx", "ly", "rx", "ry")
TRIGGERS = ("lt", "rt")
BUTTONS = {
    "A", "B", "X", "Y", "LB", "RB", "BACK", "START", "L3", "R3",
    "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
}


def clamp(value: Any, low: float, high: float, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


@dataclass
class PadState:
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0
    buttons: set[str] = field(default_factory=set)

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> "PadState":
        raw_buttons = message.get("buttons", [])
        if not isinstance(raw_buttons, list):
            raw_buttons = []
        return cls(
            **{name: clamp(message.get(name), -1.0, 1.0) for name in AXES},
            **{name: clamp(message.get(name), 0.0, 1.0) for name in TRIGGERS},
            buttons={str(value) for value in raw_buttons if str(value) in BUTTONS},
        )


class MockGamepad:
    """Used for development and tests on computers without ViGEmBus."""

    def __init__(self) -> None:
        self.state = PadState()

    def apply(self, state: PadState) -> None:
        self.state = state

    def reset(self) -> None:
        self.state = PadState()


class XboxGamepad:
    def __init__(self) -> None:
        try:
            import vgamepad as vg
        except (ImportError, OSError) as error:
            raise RuntimeError(
                "Не удалось запустить виртуальный геймпад. Установите ViGEmBus "
                "и зависимости через install.bat."
            ) from error

        self.vg = vg
        self.pad = vg.VX360Gamepad()
        self.button_map = {
            "A": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            "B": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            "X": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            "Y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            "LB": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            "RB": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            "BACK": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
            "START": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
            "L3": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
            "R3": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            "DPAD_UP": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            "DPAD_DOWN": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            "DPAD_LEFT": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            "DPAD_RIGHT": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        }

    def apply(self, state: PadState) -> None:
        self.pad.reset()
        self.pad.left_joystick_float(state.lx, state.ly)
        self.pad.right_joystick_float(state.rx, state.ry)
        self.pad.left_trigger_float(state.lt)
        self.pad.right_trigger_float(state.rt)
        for button in state.buttons:
            self.pad.press_button(self.button_map[button])
        self.pad.update()

    def reset(self) -> None:
        self.pad.reset()
        self.pad.update()


def create_gamepad(mock: bool = False):
    if mock:
        return MockGamepad()
    return XboxGamepad()
