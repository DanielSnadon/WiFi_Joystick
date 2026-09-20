"use strict";

const arena = document.querySelector("#arena");
const stageViewport = document.querySelector("#stageViewport");
const app = document.querySelector("#app");
const editButton = document.querySelector("#editButton");
const addButton = document.querySelector("#addButton");
const resetButton = document.querySelector("#resetButton");
const fullscreenButton = document.querySelector("#fullscreenButton");
const inspector = document.querySelector("#inspector");
const actionSelect = document.querySelector("#actionSelect");
const labelInput = document.querySelector("#labelInput");
const selectedName = document.querySelector("#selectedName");
const addMenu = document.querySelector("#addMenu");
const statusDot = document.querySelector("#statusDot");
const statusText = document.querySelector("#statusText");
const settingsButton = document.querySelector("#settingsButton");
const settingsMenu = document.querySelector("#settingsMenu");
const infoButton = document.querySelector("#infoButton");
const infoMenu = document.querySelector("#infoMenu");
const deviceCount = document.querySelector("#deviceCount");
const playerSlot = document.querySelector("#playerSlot");
const inputBadge = document.querySelector("#inputBadge");
const deviceNameInput = document.querySelector("#deviceName");
const slotSelect = document.querySelector("#slotSelect");
const deviceList = document.querySelector("#deviceList");
const inputModeSelect = document.querySelector("#inputModeSelect");
const mouseSensitivity = document.querySelector("#mouseSensitivity");
const mouseSensitivityOutput = document.querySelector("#mouseSensitivityOutput");
const aspectSelect = document.querySelector("#aspectSelect");
const fillRange = document.querySelector("#fillRange");
const fillOutput = document.querySelector("#fillOutput");
const marginRange = document.querySelector("#marginRange");
const marginOutput = document.querySelector("#marginOutput");
const desktopOverlay = document.querySelector("#desktopOverlay");
const captureMouseButton = document.querySelector("#captureMouseButton");

const STORAGE_KEY = "wifi-gamepad-layout-v1";
const THEME_KEY = "wifi-gamepad-theme-v1";
const STYLE_KEY = "wifi-gamepad-style-v1";
const DISPLAY_KEY = "wifi-gamepad-display-v1";
const DEVICE_ID_KEY = "wifi-gamepad-device-id-v1";
const DEVICE_NAME_KEY = "wifi-gamepad-device-name-v1";
const SLOT_KEY = "wifi-gamepad-slot-v1";
const INPUT_KEY = "wifi-gamepad-input-v1";
const THEMES = new Set(["terminal", "ice", "amber", "violet"]);
const STYLES = new Set(["soft", "pixel", "glass"]);
const BUTTON_ACTIONS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "L3", "R3"];
const STICK_ACTIONS = ["leftStick", "rightStick"];
const ACTION_LABELS = { leftStick: "L", rightStick: "R", BACK: "BACK", START: "START" };

const defaultLayout = [
  {id:"lt", type:"button", action:"LT", label:"LT", x:5, y:7, w:14, h:11},
  {id:"lb", type:"button", action:"LB", label:"LB", x:21, y:7, w:14, h:11},
  {id:"rb", type:"button", action:"RB", label:"RB", x:65, y:7, w:14, h:11},
  {id:"rt", type:"button", action:"RT", label:"RT", x:81, y:7, w:14, h:11},
  {id:"back", type:"button", action:"BACK", label:"BACK", x:41, y:22, w:8, h:11},
  {id:"start", type:"button", action:"START", label:"START", x:51, y:22, w:8, h:11},
  {id:"ls", type:"stick", action:"leftStick", label:"L", x:4, y:42, w:24, h:46},
  {id:"dpad", type:"dpad", action:"dpad", label:"", x:31, y:53, w:17, h:32},
  {id:"rs", type:"stick", action:"rightStick", label:"R", x:53, y:54, w:20, h:38},
  {id:"y", type:"button", action:"Y", label:"Y", x:82, y:34, w:8, h:15},
  {id:"x", type:"button", action:"X", label:"X", x:75, y:49, w:8, h:15},
  {id:"b", type:"button", action:"B", label:"B", x:89, y:49, w:8, h:15},
  {id:"a", type:"button", action:"A", label:"A", x:82, y:64, w:8, h:15},
];

let layout = loadLayout();
let editing = false;
let selectedId = null;
let socket = null;
let sendQueued = false;
let assignedSlot = null;
let connectedDevices = [];
const deviceId = loadDeviceId();
let deviceName = localStorage.getItem(DEVICE_NAME_KEY) || (matchMedia("(pointer: fine)").matches ? "Компьютер" : "Планшет");
let displaySettings = loadDisplaySettings();
let inputSettings = loadInputSettings();
let activeInputMode = "touch";
const desktopKeys = new Set();
const desktopMouseButtons = new Set();
const desktopMouse = {x:0, y:0, timer:null};
const interactions = new Map();
const pointerOwners = new Map();

function loadLayout() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(saved) && saved.length) return saved;
  } catch (_) {}
  return structuredClone(defaultLayout);
}

function saveLayout() { localStorage.setItem(STORAGE_KEY, JSON.stringify(layout)); }
function loadDeviceId() {
  let value = localStorage.getItem(DEVICE_ID_KEY);
  if (!value) {
    value = `device-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,10)}`;
    localStorage.setItem(DEVICE_ID_KEY, value);
  }
  return value;
}
function loadDisplaySettings() {
  try {
    return {...{aspect:"auto", fill:100, margin:0}, ...JSON.parse(localStorage.getItem(DISPLAY_KEY) || "{}")};
  } catch (_) {
    return {aspect:"auto", fill:100, margin:0};
  }
}
function loadInputSettings() {
  try {
    return {...{mode:"auto", sensitivity:100}, ...JSON.parse(localStorage.getItem(INPUT_KEY) || "{}")};
  } catch (_) {
    return {mode:"auto", sensitivity:100};
  }
}
function byId(id) { return layout.find(item => item.id === id); }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function uid() { return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2,6)}`; }

function render() {
  arena.replaceChildren();
  for (const item of layout) {
    const node = document.createElement("div");
    node.className = `control ${item.type}${item.id === selectedId ? " selected" : ""}`;
    node.dataset.id = item.id;
    node.dataset.action = item.action;
    node.style.cssText = `left:${item.x}%;top:${item.y}%;width:${item.w}%;height:${item.h}%;`;
    if (item.type === "button") node.innerHTML = `<span class="control-label"></span>`;
    if (item.type === "button") node.querySelector(".control-label").textContent = item.label || item.action;
    if (item.type === "stick") {
      node.innerHTML = '<i class="stick-ring"></i><i class="stick-knob"></i>';
    }
    if (item.type === "dpad") {
      node.innerHTML = '<i class="dpad-cross"></i><i class="dpad-center"></i><b class="dpad-mark up">▲</b><b class="dpad-mark down">▼</b><b class="dpad-mark left">◀</b><b class="dpad-mark right">▶</b>';
    }
    const handle = document.createElement("i");
    handle.className = "resize-handle";
    handle.addEventListener("pointerdown", event => beginResize(event, item));
    node.append(handle);
    node.addEventListener("pointerdown", event => editing ? beginMove(event, item) : beginControl(event, item, node));
    node.addEventListener("contextmenu", event => event.preventDefault());
    arena.append(node);
  }
  updateInspector();
}

function beginControl(event, item, node) {
  event.preventDefault();
  if (pointerOwners.has(event.pointerId)) return;
  const pressToken = Symbol("press");
  const pressedAt = performance.now();
  pointerOwners.set(event.pointerId, item.id);
  node.setPointerCapture(event.pointerId);
  if (item.type === "button") {
    interactions.set(item.id, {type:"button", action:item.action, token:pressToken});
    node.classList.add("pressed");
    vibrate();
  } else if (item.type === "stick") {
    updateStick(event, item, node);
  } else if (item.type === "dpad") {
    updateDpad(event, item, node);
  }
  if (item.type === "button") sendState();
  else queueState();

  const move = next => {
    if (item.type === "stick") updateStick(next, item, node);
    if (item.type === "dpad") updateDpad(next, item, node);
    queueState();
  };
  const end = endEvent => {
    if (endEvent.pointerId !== event.pointerId) return;
    pointerOwners.delete(event.pointerId);
    node.removeEventListener("pointermove", move);
    node.removeEventListener("pointerup", end);
    node.removeEventListener("pointercancel", end);
    const release = () => {
      const current = interactions.get(item.id);
      if (item.type === "button" && current?.token !== pressToken) return;
      interactions.delete(item.id);
      node.classList.remove("pressed", "active");
      const knob = node.querySelector(".stick-knob");
      if (knob) knob.style.transform = "translate(0,0)";
      if (item.type === "button") sendState();
      else queueState();
    };
    if (item.type === "button") setTimeout(release, Math.max(0, 90 - (performance.now() - pressedAt)));
    else release();
  };
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", end);
  node.addEventListener("pointercancel", end);
}

function localPoint(event, node) {
  const rect = node.getBoundingClientRect();
  return {x:event.clientX - rect.left - rect.width / 2, y:event.clientY - rect.top - rect.height / 2, rect};
}

function updateStick(event, item, node) {
  const {x, y, rect} = localPoint(event, node);
  const radius = Math.min(rect.width, rect.height) * .38;
  const length = Math.hypot(x, y);
  const scale = length > radius ? radius / length : 1;
  const px = x * scale, py = y * scale;
  let sx = px / radius, sy = -py / radius;
  const magnitude = Math.hypot(sx, sy);
  if (magnitude < .08) sx = sy = 0;
  interactions.set(item.id, {type:"stick", action:item.action, x:sx, y:sy});
  node.querySelector(".stick-knob").style.transform = `translate(${px}px,${py}px)`;
}

function updateDpad(event, item, node) {
  const {x, y, rect} = localPoint(event, node);
  const nx = x / (rect.width / 2), ny = y / (rect.height / 2);
  const directions = [];
  if (ny < -.26) directions.push("DPAD_UP");
  if (ny > .26) directions.push("DPAD_DOWN");
  if (nx < -.26) directions.push("DPAD_LEFT");
  if (nx > .26) directions.push("DPAD_RIGHT");
  interactions.set(item.id, {type:"dpad", directions});
  node.classList.toggle("active", directions.length > 0);
}

function currentState() {
  if (activeInputMode === "desktop") return currentDesktopState();
  const state = {lx:0, ly:0, rx:0, ry:0, lt:0, rt:0, buttons:[]};
  const buttons = new Set();
  for (const value of interactions.values()) {
    if (value.type === "button") {
      if (value.action === "LT") state.lt = 1;
      else if (value.action === "RT") state.rt = 1;
      else buttons.add(value.action);
    } else if (value.type === "stick") {
      const prefix = value.action === "rightStick" ? "r" : "l";
      state[`${prefix}x`] = value.x;
      state[`${prefix}y`] = value.y;
    } else if (value.type === "dpad") {
      value.directions.forEach(direction => buttons.add(direction));
    }
  }
  state.buttons = [...buttons];
  return state;
}

function currentDesktopState() {
  const state = {lx:0, ly:0, rx:desktopMouse.x, ry:desktopMouse.y, lt:0, rt:0, buttons:[]};
  const left = desktopKeys.has("KeyA") ? -1 : 0;
  const right = desktopKeys.has("KeyD") ? 1 : 0;
  const up = desktopKeys.has("KeyW") ? 1 : 0;
  const down = desktopKeys.has("KeyS") ? -1 : 0;
  state.lx = left + right;
  state.ly = up + down;
  if (state.lx && state.ly) { state.lx *= Math.SQRT1_2; state.ly *= Math.SQRT1_2; }
  const buttons = new Set();
  const keyMap = {
    Space:"A", KeyE:"B", KeyQ:"X", KeyR:"Y", ShiftLeft:"LB", ControlLeft:"RB",
    Enter:"START", Backspace:"BACK", KeyF:"L3", KeyC:"R3",
    ArrowUp:"DPAD_UP", ArrowDown:"DPAD_DOWN", ArrowLeft:"DPAD_LEFT", ArrowRight:"DPAD_RIGHT",
  };
  for (const [code, action] of Object.entries(keyMap)) if (desktopKeys.has(code)) buttons.add(action);
  if (desktopMouseButtons.has(0)) state.rt = 1;
  if (desktopMouseButtons.has(2)) state.lt = 1;
  if (desktopMouseButtons.has(1)) buttons.add("R3");
  if (desktopMouseButtons.has(3)) buttons.add("LB");
  if (desktopMouseButtons.has(4)) buttons.add("RB");
  state.buttons = [...buttons];
  return state;
}

function queueState() {
  if (sendQueued) return;
  sendQueued = true;
  requestAnimationFrame(() => { sendQueued = false; sendState(); });
}

function sendState() {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"state", state:currentState()}));
}

function connect() {
  const token = new URLSearchParams(location.search).get("token") || "";
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${protocol}//${location.host}/ws?token=${encodeURIComponent(token)}`);
  setStatus(false, "ПОДКЛЮЧЕНИЕ");
  socket.addEventListener("open", () => {
    setStatus(true, "РЕГИСТРАЦИЯ");
    const preferredSlot = Number(localStorage.getItem(SLOT_KEY)) || 1;
    socket.send(JSON.stringify({type:"hello", deviceId, name:deviceName, preferredSlot, inputType:activeInputMode}));
  });
  socket.addEventListener("message", event => {
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (message.type === "assigned") {
      assignedSlot = message.slot;
      localStorage.setItem(SLOT_KEY, String(assignedSlot));
      playerSlot.textContent = assignedSlot;
      slotSelect.value = String(assignedSlot);
      setStatus(true, `P${assignedSlot} ГОТОВ`);
    } else if (message.type === "devices") {
      connectedDevices = Array.isArray(message.devices) ? message.devices : [];
      renderDeviceList();
    } else if (message.type === "error") {
      alert(message.message || "Ошибка подключения устройства");
    }
  });
  socket.addEventListener("close", () => {
    assignedSlot = null;
    playerSlot.textContent = "—";
    setStatus(false, "НЕТ СВЯЗИ");
    setTimeout(connect, 1200);
  });
  socket.addEventListener("error", () => socket.close());
}

function setStatus(online, text) { statusDot.classList.toggle("online", online); statusText.textContent = text; }
setInterval(sendState, 250);

function setTheme(theme) {
  const safeTheme = THEMES.has(theme) ? theme : "terminal";
  document.documentElement.dataset.theme = safeTheme;
  localStorage.setItem(THEME_KEY, safeTheme);
}
function setControlStyle(style) {
  const safeStyle = STYLES.has(style) ? style : "soft";
  document.documentElement.dataset.controlStyle = safeStyle;
  localStorage.setItem(STYLE_KEY, safeStyle);
  refreshStyleSelection();
}
function refreshStyleSelection() {
  const theme = document.documentElement.dataset.theme;
  const style = document.documentElement.dataset.controlStyle;
  settingsMenu.querySelectorAll("[data-theme-choice]").forEach(node => node.classList.toggle("active", node.dataset.themeChoice === theme));
  settingsMenu.querySelectorAll("[data-style-choice]").forEach(node => node.classList.toggle("active", node.dataset.styleChoice === style));
}
setTheme(localStorage.getItem(THEME_KEY) || "terminal");
setControlStyle(localStorage.getItem(STYLE_KEY) || "soft");
settingsButton.addEventListener("click", () => {
  if (document.pointerLockElement) document.exitPointerLock();
  clearDesktopInput();
  refreshStyleSelection();
  settingsMenu.classList.remove("hidden");
});
settingsMenu.addEventListener("click", event => {
  if (event.target.matches("[data-settings-close]") || event.target === settingsMenu) settingsMenu.classList.add("hidden");
  const tab = event.target.closest("[data-settings-tab]");
  if (tab) {
    settingsMenu.querySelectorAll("[data-settings-tab]").forEach(node => node.classList.toggle("active", node === tab));
    settingsMenu.querySelectorAll("[data-settings-panel]").forEach(node => node.classList.toggle("active", node.dataset.settingsPanel === tab.dataset.settingsTab));
  }
  const choice = event.target.closest("[data-theme-choice]");
  if (choice) {
    setTheme(choice.dataset.themeChoice);
    refreshStyleSelection();
  }
  const styleChoice = event.target.closest("[data-style-choice]");
  if (styleChoice) setControlStyle(styleChoice.dataset.styleChoice);
});
infoButton.addEventListener("click", () => infoMenu.classList.remove("hidden"));
infoMenu.addEventListener("click", event => {
  if (event.target.matches("[data-info-close]") || event.target === infoMenu) infoMenu.classList.add("hidden");
});

function renderDeviceList() {
  deviceCount.textContent = String(connectedDevices.length);
  const occupied = new Map(connectedDevices.map(device => [device.slot, device.deviceId]));
  [...slotSelect.options].forEach(option => {
    const slot = Number(option.value);
    option.disabled = occupied.has(slot) && occupied.get(slot) !== deviceId;
  });
  const own = connectedDevices.find(device => device.deviceId === deviceId);
  if (own) {
    assignedSlot = own.slot;
    playerSlot.textContent = own.slot;
    slotSelect.value = String(own.slot);
    if (document.activeElement !== deviceNameInput) deviceNameInput.value = own.name;
  }
  deviceList.replaceChildren(...connectedDevices.map(device => {
    const row = document.createElement("div");
    row.className = `device-row${device.deviceId === deviceId ? " current" : ""}`;
    const badge = document.createElement("b");
    badge.textContent = `P${device.slot}`;
    const copy = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = device.name;
    const state = document.createElement("small");
    const source = device.inputType === "desktop" ? "КОМПЬЮТЕР" : "СЕНСОР";
    state.textContent = `${device.deviceId === deviceId ? "ЭТО УСТРОЙСТВО" : "ПОДКЛЮЧЕНО"} · ${source}`;
    copy.append(name, state);
    const dot = document.createElement("i");
    row.append(badge, copy, dot);
    return row;
  }));
}

deviceNameInput.value = deviceName;
deviceNameInput.addEventListener("change", () => {
  deviceName = deviceNameInput.value.trim().slice(0, 24) || "Планшет";
  deviceNameInput.value = deviceName;
  localStorage.setItem(DEVICE_NAME_KEY, deviceName);
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"rename", name:deviceName}));
});
slotSelect.addEventListener("change", () => {
  const slot = Number(slotSelect.value);
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"set_slot", slot}));
});

function saveDisplaySettings() {
  localStorage.setItem(DISPLAY_KEY, JSON.stringify(displaySettings));
}
function syncDisplayControls() {
  aspectSelect.value = displaySettings.aspect;
  fillRange.value = String(displaySettings.fill);
  marginRange.value = String(displaySettings.margin);
  fillOutput.textContent = `${displaySettings.fill}%`;
  marginOutput.textContent = `${displaySettings.margin}%`;
}
function fitArena() {
  const bounds = stageViewport.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const safe = Math.min(bounds.width, bounds.height) * displaySettings.margin / 100;
  let width = Math.max(1, bounds.width - safe * 2);
  let height = Math.max(1, bounds.height - safe * 2);
  const ratios = {"16:9":16/9, "16:10":16/10, "4:3":4/3};
  const ratio = ratios[displaySettings.aspect];
  if (ratio) {
    if (width / height > ratio) width = height * ratio;
    else height = width / ratio;
  }
  const fill = displaySettings.fill / 100;
  arena.style.width = `${Math.round(width * fill)}px`;
  arena.style.height = `${Math.round(height * fill)}px`;
}
function updateDisplayFromControls() {
  displaySettings = {aspect:aspectSelect.value, fill:Number(fillRange.value), margin:Number(marginRange.value)};
  syncDisplayControls();
  saveDisplaySettings();
  fitArena();
}
aspectSelect.addEventListener("change", updateDisplayFromControls);
fillRange.addEventListener("input", updateDisplayFromControls);
marginRange.addEventListener("input", updateDisplayFromControls);
document.querySelector("#resetScreenButton").addEventListener("click", () => {
  displaySettings = {aspect:"auto", fill:100, margin:0};
  syncDisplayControls(); saveDisplaySettings(); fitArena();
});
window.addEventListener("resize", fitArena);
syncDisplayControls();
requestAnimationFrame(fitArena);

function clearDesktopInput() {
  desktopKeys.clear();
  desktopMouseButtons.clear();
  desktopMouse.x = 0;
  desktopMouse.y = 0;
  if (desktopMouse.timer) clearTimeout(desktopMouse.timer);
  desktopMouse.timer = null;
  sendState();
}
function applyInputMode() {
  const requested = inputSettings.mode;
  activeInputMode = requested === "auto" ? (matchMedia("(pointer: fine)").matches ? "desktop" : "touch") : requested;
  app.classList.toggle("desktop-mode", activeInputMode === "desktop");
  desktopOverlay.classList.toggle("hidden", activeInputMode !== "desktop");
  inputBadge.textContent = activeInputMode === "desktop" ? "KEY+MOUSE" : "TOUCH";
  inputModeSelect.value = requested;
  mouseSensitivity.value = String(inputSettings.sensitivity);
  mouseSensitivityOutput.textContent = `${inputSettings.sensitivity}%`;
  interactions.clear();
  clearDesktopInput();
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"input_type", inputType:activeInputMode}));
}
function saveInputSettings() {
  localStorage.setItem(INPUT_KEY, JSON.stringify(inputSettings));
}
inputModeSelect.addEventListener("change", () => {
  inputSettings.mode = inputModeSelect.value;
  saveInputSettings();
  applyInputMode();
});
mouseSensitivity.addEventListener("input", () => {
  inputSettings.sensitivity = Number(mouseSensitivity.value);
  mouseSensitivityOutput.textContent = `${inputSettings.sensitivity}%`;
  saveInputSettings();
});
captureMouseButton.addEventListener("click", event => {
  event.stopPropagation();
  stageViewport.requestPointerLock?.();
});
document.addEventListener("pointerlockchange", () => {
  const captured = document.pointerLockElement === stageViewport;
  desktopOverlay.classList.toggle("captured", captured);
  captureMouseButton.textContent = captured ? "МЫШЬ ЗАХВАЧЕНА" : "ЗАХВАТИТЬ МЫШЬ";
  if (!captured) clearDesktopInput();
});

const desktopCodes = new Set([
  "KeyW","KeyA","KeyS","KeyD","Space","KeyE","KeyQ","KeyR","ShiftLeft","ControlLeft",
  "Enter","Backspace","KeyF","KeyC","ArrowUp","ArrowDown","ArrowLeft","ArrowRight",
]);
document.addEventListener("keydown", event => {
  if (activeInputMode !== "desktop" || document.querySelector(".modal:not(.hidden)")) return;
  if (!desktopCodes.has(event.code)) return;
  event.preventDefault();
  desktopKeys.add(event.code);
  sendState();
});
document.addEventListener("keyup", event => {
  if (activeInputMode !== "desktop" || !desktopCodes.has(event.code)) return;
  event.preventDefault();
  desktopKeys.delete(event.code);
  sendState();
});
document.addEventListener("mousemove", event => {
  if (activeInputMode !== "desktop" || document.pointerLockElement !== stageViewport) return;
  const sensitivity = inputSettings.sensitivity / 100;
  desktopMouse.x = clamp(event.movementX * .075 * sensitivity, -1, 1);
  desktopMouse.y = clamp(-event.movementY * .075 * sensitivity, -1, 1);
  sendState();
  if (desktopMouse.timer) clearTimeout(desktopMouse.timer);
  desktopMouse.timer = setTimeout(() => { desktopMouse.x = 0; desktopMouse.y = 0; sendState(); }, 42);
});
document.addEventListener("mousedown", event => {
  if (activeInputMode !== "desktop" || document.pointerLockElement !== stageViewport) return;
  event.preventDefault();
  desktopMouseButtons.add(event.button);
  sendState();
});
document.addEventListener("mouseup", event => {
  if (activeInputMode !== "desktop") return;
  desktopMouseButtons.delete(event.button);
  sendState();
});
document.addEventListener("contextmenu", event => {
  if (activeInputMode === "desktop" && document.pointerLockElement === stageViewport) event.preventDefault();
});
applyInputMode();

function beginMove(event, item) {
  event.preventDefault();
  selectedId = item.id;
  arena.querySelectorAll(".control.selected").forEach(element => element.classList.remove("selected"));
  const node = event.currentTarget;
  node.classList.add("selected");
  updateInspector();
  node.setPointerCapture(event.pointerId);
  const rect = arena.getBoundingClientRect();
  const start = {x:event.clientX, y:event.clientY, left:item.x, top:item.y};
  const move = next => {
    item.x = clamp(start.left + (next.clientX - start.x) / rect.width * 100, 0, 100 - item.w);
    item.y = clamp(start.top + (next.clientY - start.y) / rect.height * 100, 0, 100 - item.h);
    node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
  };
  const end = () => { node.removeEventListener("pointermove", move); saveLayout(); };
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", end, {once:true});
  node.addEventListener("pointercancel", end, {once:true});
}

function beginResize(event, item) {
  event.preventDefault(); event.stopPropagation();
  const node = event.currentTarget.parentElement;
  node.setPointerCapture(event.pointerId);
  const rect = arena.getBoundingClientRect();
  const start = {x:event.clientX, y:event.clientY, w:item.w, h:item.h};
  const move = next => {
    item.w = clamp(start.w + (next.clientX - start.x) / rect.width * 100, 6, 100 - item.x);
    item.h = clamp(start.h + (next.clientY - start.y) / rect.height * 100, 10, 100 - item.y);
    node.style.width = `${item.w}%`; node.style.height = `${item.h}%`;
  };
  const end = () => { node.removeEventListener("pointermove", move); saveLayout(); };
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", end, {once:true});
  node.addEventListener("pointercancel", end, {once:true});
}

function updateInspector() {
  const item = byId(selectedId);
  inspector.classList.toggle("visible", Boolean(item));
  if (!item) return;
  selectedName.textContent = item.type.toUpperCase();
  const actions = item.type === "button" ? BUTTON_ACTIONS : item.type === "stick" ? STICK_ACTIONS : ["dpad"];
  actionSelect.replaceChildren(...actions.map(action => new Option(action, action, false, action === item.action)));
  actionSelect.disabled = item.type === "dpad";
  labelInput.value = item.label || "";
  labelInput.disabled = item.type === "dpad";
}

function setEditing(value) {
  editing = value;
  interactions.clear(); queueState(); selectedId = editing ? layout[0]?.id : null;
  app.classList.toggle("editing", editing);
  render();
}
editButton.addEventListener("click", () => setEditing(false));
document.querySelector("#openEditorButton").addEventListener("click", () => {
  settingsMenu.classList.add("hidden");
  setEditing(true);
});
addButton.addEventListener("click", () => addMenu.classList.remove("hidden"));
addMenu.addEventListener("click", event => {
  if (event.target.matches("[data-close]")) addMenu.classList.add("hidden");
  const type = event.target.dataset.add;
  if (!type) return;
  const item = {id:uid(), type, action:type === "button" ? "A" : type === "stick" ? "leftStick" : "dpad", label:type === "button" ? "A" : type === "stick" ? "L" : "", x:43, y:42, w:type === "button" ? 10 : 20, h:type === "button" ? 18 : 36};
  layout.push(item); selectedId = item.id; saveLayout(); addMenu.classList.add("hidden"); render();
});
resetButton.addEventListener("click", () => {
  if (!confirm("Вернуть стандартную раскладку?")) return;
  layout = structuredClone(defaultLayout); selectedId = layout[0].id; saveLayout(); render();
});
document.querySelector("#deleteButton").addEventListener("click", () => {
  layout = layout.filter(item => item.id !== selectedId); selectedId = layout[0]?.id || null; saveLayout(); render();
});
actionSelect.addEventListener("change", () => {
  const item = byId(selectedId); if (!item) return;
  item.action = actionSelect.value; item.label = ACTION_LABELS[item.action] || item.action; saveLayout(); render();
});
labelInput.addEventListener("input", () => {
  const item = byId(selectedId); if (!item) return;
  item.label = labelInput.value.toUpperCase(); saveLayout();
  const node = arena.querySelector(`[data-id="${item.id}"]`); if (node && item.type === "button") node.querySelector(".control-label").textContent = item.label;
});
fullscreenButton.addEventListener("click", async () => {
  try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); } catch (_) {}
  requestAnimationFrame(fitArena);
});
function vibrate() { try { navigator.vibrate?.(8); } catch (_) {} }
document.addEventListener("visibilitychange", () => { if (document.hidden) { interactions.clear(); clearDesktopInput(); } });
window.addEventListener("blur", () => { interactions.clear(); clearDesktopInput(); });

render();
connect();
