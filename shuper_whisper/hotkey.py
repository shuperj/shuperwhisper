"""Global toggle hotkey using Win32 RegisterHotKey.

Uses standard Windows APIs instead of a low-level keyboard hook, so it works
without admin privileges and won't be flagged by security software.
"""

import ctypes
import ctypes.wintypes
import threading
import time
from typing import Callable, Optional

from ._win32_keys import (
    WM_HOTKEY,
    PM_REMOVE,
    get_mod_flags,
    get_vk,
    user32,
)

MODIFIER_NAMES = {
    "ctrl",
    "shift",
    "alt",
    "windows",
    "win",
    "super",
    "left ctrl",
    "right ctrl",
    "left shift",
    "right shift",
    "left alt",
    "right alt",
    "left windows",
    "right windows",
}


def _normalize_modifier(mod: str) -> str:
    """Normalize modifier names for consistency."""
    mod = mod.lower().strip()
    if mod in ("super", "win"):
        return "windows"
    return mod


def parse_hotkey(hotkey_str: str) -> tuple[list[str], str]:
    """Split a hotkey string into (modifiers, trigger_key).

    Examples:
        'ctrl+shift+space' -> (['ctrl', 'shift'], 'space')
        'windows+space'    -> (['windows'], 'space')
        'f16'              -> ([], 'f16')
    """
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    if len(parts) == 1:
        return [], parts[0]
    modifiers = [_normalize_modifier(p) for p in parts[:-1]]
    trigger = parts[-1]
    return modifiers, trigger


_HOTKEY_TRIGGER = 1


class HotkeyError(RuntimeError):
    """The hotkey couldn't be registered (bad key name or already taken)."""


class HotkeyManager:
    """Global toggle hotkey: the first press starts dictation, the next stops it.

    RegisterHotKey binds to the registering thread's message queue, so a
    dedicated thread registers the key and pumps WM_HOTKEY messages.
    """

    REGISTER_TIMEOUT = 2.0

    def __init__(self, hotkey_str: str, on_start: Callable[[], None],
                 on_stop: Callable[[], None]):
        self._hotkey_str = hotkey_str
        self._on_start = on_start
        self._on_stop = on_stop
        self._modifiers, self._trigger_key = parse_hotkey(hotkey_str)
        self._mod_flags = get_mod_flags(self._modifiers)
        self._trigger_vk = get_vk(self._trigger_key)
        self._active = False
        self._registered = False
        self._register_ok = False
        self._register_done = threading.Event()
        self._stop_event = threading.Event()
        self._pump_thread: Optional[threading.Thread] = None

    def _message_pump(self) -> None:
        self._register_ok = bool(user32.RegisterHotKey(
            None, _HOTKEY_TRIGGER, self._mod_flags, self._trigger_vk))
        self._register_done.set()
        if not self._register_ok:
            return
        msg = ctypes.wintypes.MSG()
        while not self._stop_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_TRIGGER:
                    self._on_trigger_press()
            else:
                time.sleep(0.01)
        user32.UnregisterHotKey(None, _HOTKEY_TRIGGER)

    def _on_trigger_press(self) -> None:
        if self._active:
            self._active = False
            self._on_stop()
        else:
            self._active = True
            self._on_start()

    def reset(self) -> None:
        """Forget an active session (it ended without a second press)."""
        self._active = False

    def register(self) -> None:
        if self._registered:
            return
        if not self._trigger_vk:
            raise HotkeyError(f"Unknown key '{self._trigger_key}' in hotkey '{self._hotkey_str}'")
        self._stop_event.clear()
        self._register_done.clear()
        self._pump_thread = threading.Thread(target=self._message_pump, daemon=True)
        self._pump_thread.start()
        self._register_done.wait(self.REGISTER_TIMEOUT)
        if not self._register_ok:
            self._stop_event.set()
            raise HotkeyError(f"Couldn't register '{self._hotkey_str}'. Another app may be using it.")
        self._registered = True

    def unregister(self) -> None:
        if not self._registered:
            return
        self._stop_event.set()
        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)
            self._pump_thread = None
        self._registered = False
        self._active = False

    @property
    def hotkey(self) -> str:
        return self._hotkey_str

    @property
    def active(self) -> bool:
        return self._active

    @property
    def registered(self) -> bool:
        return self._registered

    def wait(self) -> None:
        """Block until unregister() or Ctrl+C."""
        while not self._stop_event.is_set():
            self._stop_event.wait(1.0)
