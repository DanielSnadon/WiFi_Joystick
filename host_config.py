from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


BINDING_ROWS = [
    ("left_up", "Левый стик ↑", "w"),
    ("left_down", "Левый стик ↓", "s"),
    ("left_left", "Левый стик ←", "a"),
    ("left_right", "Левый стик →", "d"),
    ("A", "Кнопка A", "space"),
    ("B", "Кнопка B", "e"),
    ("X", "Кнопка X", "q"),
    ("Y", "Кнопка Y", "r"),
    ("LB", "Левый бампер", "shift_l"),
    ("RB", "Правый бампер", "ctrl_l"),
    ("LT", "Левый триггер", "z"),
    ("RT", "Правый триггер", "x"),
    ("START", "START / Menu", "enter"),
    ("BACK", "BACK / View", "backspace"),
    ("L3", "Нажатие L3", "f"),
    ("R3", "Нажатие R3", "c"),
    ("DPAD_UP", "D-pad ↑", "up"),
    ("DPAD_DOWN", "D-pad ↓", "down"),
    ("DPAD_LEFT", "D-pad ←", "left"),
    ("DPAD_RIGHT", "D-pad →", "right"),
]

DEFAULT_BINDINGS = {action: key for action, _label, key in BINDING_ROWS}
DEFAULT_MOUSE_BINDINGS = {"left": "RT", "right": "LT", "middle": "R3", "x1": "LB", "x2": "RB"}
MOUSE_ACTIONS = ("НЕТ", "RT", "LT", "A", "B", "X", "Y", "LB", "RB", "L3", "R3")

DEFAULT_SETTINGS = {
    "slot": 1,
    "sensitivity": 100,
    "countdown": 3,
    "block_input": True,
    "bindings": DEFAULT_BINDINGS,
    "mouse_bindings": DEFAULT_MOUSE_BINDINGS,
}


def normalize_key_name(value: str) -> str:
    aliases = {
        "return": "enter",
        "control_l": "ctrl_l",
        "control_r": "ctrl_r",
        "prior": "page_up",
        "next": "page_down",
    }
    cleaned = str(value or "").removeprefix("Key.").lower()
    return aliases.get(cleaned, cleaned)


def load_settings(path: Path) -> dict:
    settings = deepcopy(DEFAULT_SETTINGS)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return settings
    if not isinstance(saved, dict):
        return settings
    try:
        settings["slot"] = min(4, max(1, int(saved.get("slot", settings["slot"]))))
        settings["sensitivity"] = min(200, max(25, int(saved.get("sensitivity", settings["sensitivity"]))))
        settings["countdown"] = min(10, max(0, int(saved.get("countdown", settings["countdown"]))))
    except (TypeError, ValueError):
        pass
    settings["block_input"] = bool(saved.get("block_input", settings["block_input"]))
    if isinstance(saved.get("bindings"), dict):
        for action in DEFAULT_BINDINGS:
            value = normalize_key_name(saved["bindings"].get(action, ""))
            if value and value not in {"f9", "f10"}:
                settings["bindings"][action] = value
    if isinstance(saved.get("mouse_bindings"), dict):
        for button in DEFAULT_MOUSE_BINDINGS:
            value = str(saved["mouse_bindings"].get(button, "НЕТ")).upper()
            settings["mouse_bindings"][button] = value if value in MOUSE_ACTIONS else DEFAULT_MOUSE_BINDINGS[button]
    return settings


def save_settings(path: Path, settings: dict) -> None:
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

