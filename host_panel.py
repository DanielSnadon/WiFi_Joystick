from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk

import aiohttp
from PIL import Image, ImageTk
from pynput import keyboard, mouse

from host_config import (
    BINDING_ROWS,
    DEFAULT_BINDINGS,
    DEFAULT_MOUSE_BINDINGS,
    MOUSE_ACTIONS,
    load_settings,
    normalize_key_name,
    save_settings,
)


ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "host-settings.json"
FONT = "Segoe UI Variable"
BG = "#080b10"
PANEL = "#101720"
PANEL_2 = "#17212c"
TEXT = "#eef7f1"
MUTED = "#8ea19a"
ACCENT = "#6ff59a"
LINE = "#2d423b"


class WindowsPoint(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def key_name(value) -> str:
    if isinstance(value, keyboard.KeyCode):
        return normalize_key_name(value.char or "")
    return normalize_key_name(str(value))


def display_key(value: str) -> str:
    names = {
        "space": "SPACE", "enter": "ENTER", "backspace": "BACKSPACE",
        "shift_l": "LEFT SHIFT", "shift_r": "RIGHT SHIFT",
        "ctrl_l": "LEFT CTRL", "ctrl_r": "RIGHT CTRL",
        "up": "ARROW ↑", "down": "ARROW ↓", "left": "ARROW ←", "right": "ARROW →",
    }
    return names.get(value, value.upper())


def windows_cursor_position() -> tuple[int, int] | None:
    if sys.platform != "win32":
        return None
    point = WindowsPoint()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return None
    return point.x, point.y


class WindowsHotkeys:
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_NOREPEAT = 0x4000
    VK_F9 = 0x78
    VK_F10 = 0x79

    def __init__(self, activate, release) -> None:
        self.activate = activate
        self.release = release
        self.thread_id = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        user32.RegisterHotKey(None, 1, self.MOD_NOREPEAT, self.VK_F9)
        user32.RegisterHotKey(None, 2, self.MOD_NOREPEAT, self.VK_F10)
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == self.WM_HOTKEY:
                callback = self.activate if message.wParam == 1 else self.release
                threading.Thread(target=callback, daemon=True).start()
        user32.UnregisterHotKey(None, 1)
        user32.UnregisterHotKey(None, 2)

    def stop(self) -> None:
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, self.WM_QUIT, 0, 0)


class HostInput:
    def __init__(self, settings: dict) -> None:
        self.lock = threading.RLock()
        self.keys: set[str] = set()
        self.mouse_buttons: set[str] = set()
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.mouse_time = 0.0
        self.last_mouse_position: tuple[int, int] | None = None
        self.enabled = False
        self.emergency_callback = None
        self.apply_settings(settings)

    def apply_settings(self, settings: dict) -> None:
        with self.lock:
            self.sensitivity = settings["sensitivity"] / 100
            self.bindings = dict(settings["bindings"])
            self.mouse_bindings = dict(settings["mouse_bindings"])

    def reset(self) -> None:
        with self.lock:
            self.keys.clear()
            self.mouse_buttons.clear()
            self.mouse_x = self.mouse_y = self.mouse_time = 0.0
            self.last_mouse_position = None

    def snapshot(self) -> dict:
        with self.lock:
            if not self.enabled:
                return {"lx": 0, "ly": 0, "rx": 0, "ry": 0, "lt": 0, "rt": 0, "buttons": []}
            pressed = lambda action: self.bindings.get(action) in self.keys
            lx = float(pressed("left_right") - pressed("left_left"))
            ly = float(pressed("left_up") - pressed("left_down"))
            if lx and ly:
                lx *= 2 ** -0.5
                ly *= 2 ** -0.5
            if time.monotonic() - self.mouse_time > 0.055:
                self.mouse_x = self.mouse_y = 0.0
            buttons = set()
            lt = 1.0 if pressed("LT") else 0.0
            rt = 1.0 if pressed("RT") else 0.0
            excluded = {"left_up", "left_down", "left_left", "left_right", "LT", "RT"}
            for action in DEFAULT_BINDINGS:
                if action not in excluded and pressed(action):
                    buttons.add(action)
            for button in self.mouse_buttons:
                action = self.mouse_bindings.get(button, "НЕТ")
                if action == "LT":
                    lt = 1.0
                elif action == "RT":
                    rt = 1.0
                elif action != "НЕТ":
                    buttons.add(action)
            return {"lx": lx, "ly": ly, "rx": self.mouse_x, "ry": self.mouse_y, "lt": lt, "rt": rt, "buttons": sorted(buttons)}

    def on_key_press(self, value, *_injected):
        name = key_name(value)
        if name == "f10":
            if self.emergency_callback:
                threading.Thread(target=self.emergency_callback, daemon=True).start()
            return False
        with self.lock:
            self.keys.add(name)
        return True

    def on_key_release(self, value, *_injected):
        with self.lock:
            self.keys.discard(key_name(value))
        return True

    def on_mouse_move(self, x: int, y: int, *_injected) -> None:
        with self.lock:
            anchor = windows_cursor_position() or self.last_mouse_position
            if anchor is not None:
                dx, dy = x - anchor[0], y - anchor[1]
                if dx == 0 and dy == 0 and self.last_mouse_position is not None:
                    dx, dy = x - self.last_mouse_position[0], y - self.last_mouse_position[1]
                self.mouse_x = clamp(dx * 0.065 * self.sensitivity)
                self.mouse_y = clamp(-dy * 0.065 * self.sensitivity)
                self.mouse_time = time.monotonic()
            self.last_mouse_position = (x, y)

    def on_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool, *_injected) -> None:
        name = str(button).removeprefix("Button.").lower()
        with self.lock:
            if pressed:
                self.mouse_buttons.add(name)
            else:
                self.mouse_buttons.discard(name)


class HostPanel:
    def __init__(self, token: str, port: int, connection_url: str, qr_path: Path | None) -> None:
        self.token = token
        self.port = port
        self.connection_url = connection_url
        self.qr_path = qr_path
        self.settings = load_settings(SETTINGS_PATH)
        self.input = HostInput(self.settings)
        self.input.emergency_callback = self.disable_capture
        self.stop_event = threading.Event()
        self.connected = False
        self.requested_slot = self.settings["slot"]
        self.capture_lock = threading.Lock()
        self.keyboard_listener = None
        self.mouse_listener = None
        self.binding_buttons: dict[str, tk.Button] = {}
        self.listening_action = None
        self.last_external_window = None

        self.root = tk.Tk()
        self.root.title("Wi-Fi Gamepad — Host Control")
        self.root.geometry("700x720")
        self.root.minsize(620, 620)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="ПОДКЛЮЧЕНИЕ К СЕРВЕРУ")
        self.slot_var = tk.StringVar(value=f"P{self.settings['slot']}")
        self.sensitivity_var = tk.IntVar(value=self.settings["sensitivity"])
        self.countdown_var = tk.IntVar(value=self.settings["countdown"])
        self.block_input_var = tk.BooleanVar(value=self.settings["block_input"])
        self.mode_var = tk.StringVar(value="ГОТОВ К ЗАПУСКУ")
        self.mouse_vars = {name: tk.StringVar(value=value) for name, value in self.settings["mouse_bindings"].items()}
        self.build_ui()
        self.root.bind("<KeyPress>", self.capture_binding_key, add="+")
        self.root.after(250, self.track_foreground_window)

        if sys.platform == "win32":
            self.hotkeys = WindowsHotkeys(self.activate_from_hotkey, self.disable_capture)
        else:
            self.hotkeys = keyboard.GlobalHotKeys({"<f9>": self.activate_from_hotkey, "<f10>": self.disable_capture})
        self.hotkeys.start()
        threading.Thread(target=self.network_thread, daemon=True).start()

    def configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 10), font=(FONT, 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", PANEL_2)], foreground=[("selected", ACCENT)])
        style.configure("Dark.TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=ACCENT, padding=7)
        style.configure("Dark.Horizontal.TScale", background=BG, troughcolor=PANEL_2)
        style.configure("Dark.TCheckbutton", background=BG, foreground=TEXT, font=(FONT, 10))

    def build_ui(self) -> None:
        self.configure_styles()
        header = tk.Frame(self.root, bg=BG, padx=24, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="WG  HOST CONTROL", bg=BG, fg=ACCENT, font=(FONT, 18, "bold")).pack(anchor="w")
        tk.Label(header, textvariable=self.status_var, bg=BG, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w", pady=(3, 0))
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        game_tab = tk.Frame(notebook, bg=BG, padx=18, pady=18)
        layout_tab = tk.Frame(notebook, bg=BG)
        connection_tab = tk.Frame(notebook, bg=BG, padx=20, pady=18)
        notebook.add(game_tab, text="ИГРА")
        notebook.add(layout_tab, text="УПРАВЛЕНИЕ")
        notebook.add(connection_tab, text="ПОДКЛЮЧЕНИЕ")
        self.build_game_tab(game_tab)
        self.build_layout_tab(layout_tab)
        self.build_connection_tab(connection_tab)

    def label(self, parent, text: str, muted: bool = False, **kwargs):
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", BG), fg=MUTED if muted else TEXT, font=(FONT, kwargs.pop("size", 10), kwargs.pop("weight", "normal")), **kwargs)

    def build_game_tab(self, parent) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        self.label(row, "ИГРОВОЙ СЛОТ", weight="bold").pack(side="left")
        slot_box = ttk.Combobox(row, textvariable=self.slot_var, values=("P1", "P2", "P3", "P4"), state="readonly", width=7, style="Dark.TCombobox")
        slot_box.pack(side="right")
        slot_box.bind("<<ComboboxSelected>>", self.change_slot)
        self.label(parent, "ЧУВСТВИТЕЛЬНОСТЬ МЫШИ", weight="bold").pack(anchor="w", pady=(22, 6))
        ttk.Scale(parent, from_=25, to=200, variable=self.sensitivity_var, command=self.change_sensitivity, style="Dark.Horizontal.TScale").pack(fill="x")
        countdown_row = tk.Frame(parent, bg=BG)
        countdown_row.pack(fill="x", pady=(22, 0))
        self.label(countdown_row, "ЗАДЕРЖКА ПЕРЕД ЗАХВАТОМ", weight="bold").pack(side="left")
        countdown = ttk.Combobox(countdown_row, textvariable=self.countdown_var, values=(0, 1, 2, 3, 5, 10), state="readonly", width=7, style="Dark.TCombobox")
        countdown.pack(side="right")
        countdown.bind("<<ComboboxSelected>>", self.change_countdown)
        ttk.Checkbutton(parent, text="Блокировать исходные клавиатуру и мышь", variable=self.block_input_var, command=self.change_block_input, style="Dark.TCheckbutton").pack(anchor="w", pady=(20, 8))
        self.label(parent, "Не даёт игре одновременно видеть обычную клавиатуру и виртуальный геймпад.", muted=True, wraplength=560, justify="left").pack(anchor="w")
        tk.Label(parent, textvariable=self.mode_var, bg=PANEL, fg=MUTED, font=(FONT, 14, "bold"), padx=12, pady=14).pack(fill="x", pady=(22, 12))
        self.capture_button = tk.Button(parent, text="СВЕРНУТЬ ПАНЕЛЬ И ЗАПУСТИТЬ", command=self.start_for_game, bg=ACCENT, fg="#061009", activebackground="#a3ffbd", relief="flat", font=(FONT, 12, "bold"), pady=12)
        self.capture_button.pack(fill="x")
        tk.Button(parent, text="ОТКЛЮЧИТЬ  [F10]", command=self.disable_capture, bg=PANEL_2, fg=TEXT, activebackground=LINE, activeforeground="#ffffff", relief="flat", font=(FONT, 10, "bold"), pady=10).pack(fill="x", pady=(8, 18))
        instructions = (
            "1. Настрой слот и раскладку.\n"
            "2. Открой игру — она может оставаться позади панели.\n"
            "3. Нажми большую кнопку: панель свернётся и вернёт фокус игре.\n"
            "4. После отсчёта управление включится автоматически.\n"
            "5. F10 всегда освобождает клавиатуру и мышь."
        )
        self.label(parent, instructions, muted=True, bg=PANEL, justify="left", anchor="nw", padx=14, pady=14).pack(fill="both", expand=True)

    def build_layout_tab(self, parent) -> None:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=BG, padx=18, pady=16)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw", tags="content")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure("content", width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.label(content, "КЛАВИАТУРА → ДЖОЙСТИК", weight="bold", size=12).pack(anchor="w")
        self.label(content, "Нажми на назначенную клавишу справа, затем нажми новую. F9 и F10 зарезервированы.", muted=True, wraplength=590, justify="left").pack(anchor="w", pady=(4, 14))
        grid = tk.Frame(content, bg=BG)
        grid.pack(fill="x")
        for index, (action, title, _default) in enumerate(BINDING_ROWS):
            row, column = index % 10, index // 10
            card = tk.Frame(grid, bg=PANEL, padx=10, pady=8)
            card.grid(row=row, column=column, padx=5, pady=4, sticky="ew")
            grid.grid_columnconfigure(column, weight=1)
            self.label(card, title, bg=PANEL, size=9).pack(side="left")
            button = tk.Button(card, text=display_key(self.settings["bindings"][action]), command=lambda action=action: self.listen_for_binding(action), bg=PANEL_2, fg=ACCENT, relief="flat", font=(FONT, 8, "bold"), padx=8, pady=6)
            button.pack(side="right")
            self.binding_buttons[action] = button
        self.label(content, "КНОПКИ МЫШИ", weight="bold", size=12).pack(anchor="w", pady=(20, 8))
        mouse_names = {"left": "Левая", "right": "Правая", "middle": "Средняя", "x1": "Боковая 1", "x2": "Боковая 2"}
        mouse_grid = tk.Frame(content, bg=BG)
        mouse_grid.pack(fill="x")
        for index, (button, title) in enumerate(mouse_names.items()):
            card = tk.Frame(mouse_grid, bg=PANEL, padx=10, pady=8)
            card.grid(row=index // 2, column=index % 2, padx=5, pady=4, sticky="ew")
            mouse_grid.grid_columnconfigure(index % 2, weight=1)
            self.label(card, title, bg=PANEL, size=9).pack(side="left")
            box = ttk.Combobox(card, textvariable=self.mouse_vars[button], values=MOUSE_ACTIONS, state="readonly", width=8, style="Dark.TCombobox")
            box.pack(side="right")
            box.bind("<<ComboboxSelected>>", self.change_mouse_bindings)
        tk.Button(content, text="ВЕРНУТЬ СТАНДАРТНУЮ РАСКЛАДКУ", command=self.reset_bindings, bg=PANEL_2, fg=TEXT, relief="flat", font=(FONT, 9, "bold"), pady=9).pack(fill="x", pady=(18, 6))

    def build_connection_tab(self, parent) -> None:
        self.label(parent, "ПОДКЛЮЧИТЬ ПЛАНШЕТ ИЛИ КОМПЬЮТЕР", weight="bold", size=12).pack(anchor="w")
        self.label(parent, "Устройство должно находиться в той же Wi-Fi-сети.", muted=True).pack(anchor="w", pady=(4, 14))
        if self.qr_path and self.qr_path.exists():
            image = Image.open(self.qr_path).resize((310, 310), Image.Resampling.NEAREST)
            self.qr_image = ImageTk.PhotoImage(image)
            tk.Label(parent, image=self.qr_image, bg="#ffffff", padx=12, pady=12).pack(pady=(0, 16))
        entry = tk.Entry(parent, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT, 10), justify="center")
        entry.insert(0, self.connection_url)
        entry.configure(state="readonly", readonlybackground=PANEL)
        entry.pack(fill="x", ipady=11)
        tk.Button(parent, text="СКОПИРОВАТЬ АДРЕС", command=self.copy_address, bg=PANEL_2, fg=ACCENT, relief="flat", font=(FONT, 10, "bold"), pady=10).pack(fill="x", pady=(10, 0))

    def ui(self, callback) -> None:
        try:
            self.root.after(0, callback)
        except RuntimeError:
            pass

    def persist(self) -> None:
        try:
            save_settings(SETTINGS_PATH, self.settings)
        except OSError:
            self.set_status("НЕ УДАЛОСЬ СОХРАНИТЬ НАСТРОЙКИ")

    def set_status(self, text: str) -> None:
        self.ui(lambda: self.status_var.set(text))

    def change_slot(self, _event=None) -> None:
        self.requested_slot = int(self.slot_var.get()[1:])
        self.settings["slot"] = self.requested_slot
        self.persist()

    def change_sensitivity(self, _value=None) -> None:
        self.settings["sensitivity"] = int(self.sensitivity_var.get())
        self.input.apply_settings(self.settings)
        self.persist()

    def change_countdown(self, _event=None) -> None:
        self.settings["countdown"] = int(self.countdown_var.get())
        self.persist()

    def change_block_input(self) -> None:
        self.settings["block_input"] = bool(self.block_input_var.get())
        self.persist()

    def listen_for_binding(self, action: str) -> None:
        if self.listening_action and self.listening_action in self.binding_buttons:
            old = self.listening_action
            self.binding_buttons[old].configure(text=display_key(self.settings["bindings"][old]))
        self.listening_action = action
        self.binding_buttons[action].configure(text="НАЖМИ...")
        self.binding_buttons[action].focus_set()

    def capture_binding_key(self, event):
        if not self.listening_action:
            return None
        key = normalize_key_name(event.keysym)
        if key in {"f9", "f10"}:
            self.set_status("F9 И F10 ЗАРЕЗЕРВИРОВАНЫ")
            return "break"
        action = self.listening_action
        self.settings["bindings"][action] = key
        self.binding_buttons[action].configure(text=display_key(key))
        self.listening_action = None
        self.input.apply_settings(self.settings)
        self.persist()
        return "break"

    def change_mouse_bindings(self, _event=None) -> None:
        self.settings["mouse_bindings"] = {name: variable.get() for name, variable in self.mouse_vars.items()}
        self.input.apply_settings(self.settings)
        self.persist()

    def reset_bindings(self) -> None:
        self.settings["bindings"] = dict(DEFAULT_BINDINGS)
        self.settings["mouse_bindings"] = dict(DEFAULT_MOUSE_BINDINGS)
        for action, button in self.binding_buttons.items():
            button.configure(text=display_key(self.settings["bindings"][action]))
        for name, variable in self.mouse_vars.items():
            variable.set(self.settings["mouse_bindings"][name])
        self.input.apply_settings(self.settings)
        self.persist()

    def copy_address(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.connection_url)
        self.status_var.set("АДРЕС СКОПИРОВАН")

    def track_foreground_window(self) -> None:
        if sys.platform == "win32":
            foreground = ctypes.windll.user32.GetForegroundWindow()
            panel_window = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), 2)
            if foreground and foreground != panel_window and ctypes.windll.user32.IsWindowVisible(foreground):
                self.last_external_window = foreground
        if not self.stop_event.is_set():
            self.root.after(250, self.track_foreground_window)

    def restore_game_focus(self) -> None:
        if sys.platform == "win32" and self.last_external_window:
            ctypes.windll.user32.ShowWindow(self.last_external_window, 9)
            ctypes.windll.user32.SetForegroundWindow(self.last_external_window)

    def start_for_game(self) -> None:
        if not self.connected:
            self.status_var.set("НЕТ СВЯЗИ — ДОЖДИТЕСЬ ПОДКЛЮЧЕНИЯ")
            return
        delay = int(self.countdown_var.get())
        self.mode_var.set(f"ЗАПУСК ЧЕРЕЗ {delay} СЕК.")
        self.root.iconify()
        self.root.after(120, self.restore_game_focus)
        self.root.after(max(250, delay * 1000), lambda: threading.Thread(target=self.enable_capture, daemon=True).start())

    def activate_from_hotkey(self) -> None:
        if self.connected and not self.input.enabled:
            self.enable_capture()

    def enable_capture(self) -> None:
        with self.capture_lock:
            if self.input.enabled or not self.connected:
                return
            self.input.reset()
            self.input.apply_settings(self.settings)
            self.input.enabled = True
            suppress = bool(self.settings["block_input"])
            self.keyboard_listener = keyboard.Listener(on_press=self.input.on_key_press, on_release=self.input.on_key_release, suppress=suppress)
            self.mouse_listener = mouse.Listener(on_move=self.input.on_mouse_move, on_click=self.input.on_mouse_click, suppress=suppress)
            self.keyboard_listener.start()
            self.mouse_listener.start()
        self.ui(lambda: self.mode_var.set("АКТИВНО · F10 ДЛЯ ВЫХОДА"))
        self.ui(lambda: self.capture_button.configure(bg="#214a30", text="УПРАВЛЕНИЕ АКТИВНО"))

    def disable_capture(self) -> None:
        with self.capture_lock:
            if not self.input.enabled:
                return
            self.input.enabled = False
            listeners = (self.keyboard_listener, self.mouse_listener)
            self.keyboard_listener = self.mouse_listener = None
            for listener in listeners:
                if listener:
                    listener.stop()
            self.input.reset()
        self.ui(lambda: self.mode_var.set("ОТКЛЮЧЕНО · МОЖНО ВЕРНУТЬСЯ В ПАНЕЛЬ"))
        self.ui(lambda: self.capture_button.configure(bg=ACCENT, text="СВЕРНУТЬ ПАНЕЛЬ И ЗАПУСТИТЬ"))

    async def receiver(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for message in ws:
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                payload = json.loads(message.data)
            except (json.JSONDecodeError, TypeError):
                continue
            if payload.get("type") == "assigned":
                slot = int(payload["slot"])
                self.requested_slot = slot
                self.settings["slot"] = slot
                self.persist()
                self.ui(lambda slot=slot: self.slot_var.set(f"P{slot}"))
                self.set_status(f"ПОДКЛЮЧЕНО · ВИРТУАЛЬНЫЙ КОНТРОЛЛЕР P{slot}")
            elif payload.get("type") == "error":
                self.set_status(str(payload.get("message", "ОШИБКА ПОДКЛЮЧЕНИЯ")).upper())
            elif payload.get("type") == "devices":
                own = next((item for item in payload.get("devices", []) if item.get("deviceId") == "host-native-controller"), None)
                if own:
                    slot = int(own["slot"])
                    self.requested_slot = slot
                    self.ui(lambda slot=slot: self.slot_var.set(f"P{slot}"))

    async def network(self) -> None:
        url = f"http://127.0.0.1:{self.port}/ws?token={self.token}"
        async with aiohttp.ClientSession() as session:
            while not self.stop_event.is_set():
                try:
                    async with session.ws_connect(url, heartbeat=15) as ws:
                        self.connected = True
                        await ws.receive_json()
                        await ws.send_json({"type": "hello", "deviceId": "host-native-controller", "name": "Хост-компьютер", "preferredSlot": self.requested_slot, "inputType": "desktop"})
                        receive_task = asyncio.create_task(self.receiver(ws))
                        sent_slot = self.requested_slot
                        try:
                            while not self.stop_event.is_set() and not ws.closed:
                                if self.requested_slot != sent_slot:
                                    sent_slot = self.requested_slot
                                    await ws.send_json({"type": "set_slot", "slot": sent_slot})
                                await ws.send_json({"type": "state", "state": self.input.snapshot()})
                                await asyncio.sleep(1 / 60)
                        finally:
                            receive_task.cancel()
                            await asyncio.gather(receive_task, return_exceptions=True)
                except (aiohttp.ClientError, OSError, asyncio.TimeoutError):
                    self.connected = False
                    self.disable_capture()
                    self.set_status("ОЖИДАНИЕ СЕРВЕРА")
                    await asyncio.sleep(1)
            self.connected = False

    def network_thread(self) -> None:
        asyncio.run(self.network())

    def close(self) -> None:
        self.disable_capture()
        self.stop_event.set()
        self.hotkeys.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Native host keyboard and mouse controller")
    parser.add_argument("--token", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--url", default="")
    parser.add_argument("--qr", default="")
    args = parser.parse_args()
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
    HostPanel(args.token, args.port, args.url, Path(args.qr) if args.qr else None).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
