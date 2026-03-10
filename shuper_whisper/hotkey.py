"""Global hotkey management using Win32 RegisterHotKey + GetAsyncKeyState.

Uses standard Windows APIs instead of low-level keyboard hooks, so it works
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
    is_key_down,
    is_modifier_down,
    user32,
)

kernel32 = ctypes.windll.kernel32

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


# Hotkey ID constants
_HOTKEY_TRIGGER = 1
_HOTKEY_ARROW_UP = 2
_HOTKEY_ARROW_DOWN = 3


class HotkeyManager:
    """Manages global hotkey registration with smart hold/toggle behavior.

    Uses Win32 RegisterHotKey for the trigger (fires on key-down) and
    GetAsyncKeyState polling to detect key release for hold vs toggle.

    Intelligently detects user intent:
    - Quick tap (release < 200ms): Toggle mode - press again to stop
    - Hold (release > 200ms): Hold mode - release stops recording

    Args:
        hotkey_str: Hotkey combination string (e.g. "ctrl+shift+space").
        on_start: Called when recording should begin.
        on_stop: Called when recording should end.
        mode: Kept for backwards compatibility but ignored (always smart mode).
    """

    TOGGLE_THRESHOLD = 0.2  # 200ms - threshold for quick tap vs hold

    def __init__(
        self,
        hotkey_str: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        mode: str = "smart",
    ):
        self._hotkey_str = hotkey_str
        self._on_start = on_start
        self._on_stop = on_stop
        self._mode = "smart"  # Always smart mode now
        self._modifiers, self._trigger_key = parse_hotkey(hotkey_str)
        self._recording = False
        self._toggle_active = False
        self._registered = False
        self._arrow_hooks: list[int] = []  # Track registered arrow hotkey IDs
        self._press_time: Optional[float] = None

        # Win32 specifics
        self._mod_flags = get_mod_flags(self._modifiers)
        self._trigger_vk = get_vk(self._trigger_key)
        self._pump_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._command_queue: list[Callable] = []

        # Arrow key callbacks
        self._on_arrow_up: Optional[Callable[[], None]] = None
        self._on_arrow_down: Optional[Callable[[], None]] = None

    def _message_pump(self) -> None:
        """Win32 message loop — runs on a dedicated thread.

        RegisterHotKey binds to the calling thread's message queue, so both
        registration and message processing happen here.
        """
        # Register the main trigger hotkey
        if not user32.RegisterHotKey(None, _HOTKEY_TRIGGER,
                                     self._mod_flags, self._trigger_vk):
            err = kernel32.GetLastError()
            print(f"[hotkey] Failed to register hotkey '{self._hotkey_str}' "
                  f"(error {err}). Is another app using it?")
            return

        msg = ctypes.wintypes.MSG()
        while not self._stop_event.is_set():
            # Process any queued commands (arrow key register/unregister)
            while self._command_queue:
                cmd = self._command_queue.pop(0)
                cmd()

            # Non-blocking message check
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    if hotkey_id == _HOTKEY_TRIGGER:
                        self._on_trigger_press()
                    elif hotkey_id == _HOTKEY_ARROW_UP and self._on_arrow_up:
                        self._on_arrow_up()
                    elif hotkey_id == _HOTKEY_ARROW_DOWN and self._on_arrow_down:
                        self._on_arrow_down()
            else:
                time.sleep(0.01)  # 10ms — responsive without busy-waiting

        # Cleanup all hotkeys
        user32.UnregisterHotKey(None, _HOTKEY_TRIGGER)
        user32.UnregisterHotKey(None, _HOTKEY_ARROW_UP)
        user32.UnregisterHotKey(None, _HOTKEY_ARROW_DOWN)

    def _on_trigger_press(self) -> None:
        """Called when WM_HOTKEY fires for the trigger key."""
        # If already recording in toggle mode, stop
        if self._recording and self._toggle_active:
            self._recording = False
            self._toggle_active = False
            self._on_stop()
            return

        # Start recording
        if not self._recording:
            self._recording = True
            self._press_time = time.time()
            self._on_start()

            # Start polling for key release (determines hold vs toggle)
            threading.Thread(target=self._poll_release, daemon=True).start()

    def _poll_release(self) -> None:
        """Poll GetAsyncKeyState to detect trigger key release for hold mode."""
        # Small initial delay — RegisterHotKey fires on key-down, and
        # GetAsyncKeyState needs a moment to reflect the pressed state.
        time.sleep(0.05)

        while self._recording and not self._stop_event.is_set():
            trigger_down = is_key_down(self._trigger_vk)

            # Also check if modifiers were released (hold-mode cancel)
            modifiers_down = all(
                is_modifier_down(mod) for mod in self._modifiers
            ) if self._modifiers else True

            if not trigger_down or not modifiers_down:
                hold_time = time.time() - self._press_time if self._press_time else 0

                if hold_time < self.TOGGLE_THRESHOLD:
                    self._toggle_active = True
                    print(f"Toggle mode: press hotkey again to stop (held {hold_time:.2f}s)")
                else:
                    self._recording = False
                    self._toggle_active = False
                    reason = "trigger" if not trigger_down else "modifier"
                    print(f"Hold mode: stopping on {reason} release (held {hold_time:.2f}s)")
                    self._on_stop()
                return

            time.sleep(0.05)  # 50ms polling interval

    def register(self) -> None:
        """Register the hotkey handlers. Call once after setup."""
        if self._registered:
            return
        self._stop_event.clear()
        self._pump_thread = threading.Thread(target=self._message_pump, daemon=True)
        self._pump_thread.start()
        self._registered = True

    def register_arrow_keys(
        self,
        on_up: Callable[[], None],
        on_down: Callable[[], None],
    ) -> None:
        """Register up/down arrow key handlers for format mode cycling."""
        self.unregister_arrow_keys()
        self._on_arrow_up = on_up
        self._on_arrow_down = on_down

        vk_up = get_vk("up")
        vk_down = get_vk("down")

        def _register():
            from ._win32_keys import MOD_NOREPEAT
            user32.RegisterHotKey(None, _HOTKEY_ARROW_UP, MOD_NOREPEAT, vk_up)
            user32.RegisterHotKey(None, _HOTKEY_ARROW_DOWN, MOD_NOREPEAT, vk_down)

        self._command_queue.append(_register)
        self._arrow_hooks = [_HOTKEY_ARROW_UP, _HOTKEY_ARROW_DOWN]

    def unregister_arrow_keys(self) -> None:
        """Remove arrow key handlers."""
        self._on_arrow_up = None
        self._on_arrow_down = None

        if self._arrow_hooks:
            def _unregister():
                user32.UnregisterHotKey(None, _HOTKEY_ARROW_UP)
                user32.UnregisterHotKey(None, _HOTKEY_ARROW_DOWN)

            self._command_queue.append(_unregister)
            self._arrow_hooks.clear()

    def unregister(self) -> None:
        """Remove all hotkey handlers."""
        if not self._registered:
            return
        self._stop_event.set()
        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)
            self._pump_thread = None
        self._registered = False
        self._recording = False
        self._toggle_active = False
        self._press_time = None
        self._on_arrow_up = None
        self._on_arrow_down = None
        self._arrow_hooks.clear()
        self._command_queue.clear()

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value

    def wait(self) -> None:
        """Block the current thread until Ctrl+C or program exit."""
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(1.0)
        except KeyboardInterrupt:
            raise
