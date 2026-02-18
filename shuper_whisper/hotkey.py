"""Global hotkey management using the keyboard library."""

import time
from typing import Callable, Optional

import keyboard

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
    """Normalize modifier names for keyboard library compatibility."""
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


class HotkeyManager:
    """Manages global hotkey registration with smart hold/toggle behavior.

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
        self._arrow_hooks: list = []
        self._key_is_down = False
        self._press_time: Optional[float] = None

    def _modifiers_pressed(self) -> bool:
        """Check if all required modifier keys are currently held."""
        return all(keyboard.is_pressed(mod) for mod in self._modifiers)

    def _on_trigger_press(self, event) -> None:
        if not self._modifiers_pressed():
            return

        # Suppress key repeat
        if self._key_is_down:
            return
        self._key_is_down = True
        self._press_time = time.time()

        # If already recording in toggle mode, stop
        if self._recording and self._toggle_active:
            self._recording = False
            self._toggle_active = False
            self._on_stop()
        # Otherwise, start recording
        elif not self._recording:
            self._recording = True
            self._on_start()

    def _on_trigger_release(self, event) -> None:
        self._key_is_down = False

        if not self._recording:
            return

        # Calculate hold duration
        hold_time = time.time() - self._press_time if self._press_time else 0

        # Quick tap: enter toggle mode (don't stop recording yet)
        if hold_time < self.TOGGLE_THRESHOLD:
            self._toggle_active = True
            print(f"Toggle mode: press hotkey again to stop (held {hold_time:.2f}s)")
        # Long hold: stop recording immediately
        else:
            self._recording = False
            self._toggle_active = False
            print(f"Hold mode: stopping on release (held {hold_time:.2f}s)")
            self._on_stop()

    def _on_modifier_release(self, event) -> None:
        # If recording and not in toggle mode, stop (modifier released during hold)
        if self._recording and not self._toggle_active:
            self._recording = False
            print("Hold mode: stopping on modifier release")
            self._on_stop()

    def register(self) -> None:
        """Register the hotkey handlers. Call once after setup."""
        if self._registered:
            return
        keyboard.on_press_key(self._trigger_key, self._on_trigger_press, suppress=False)
        keyboard.on_release_key(
            self._trigger_key, self._on_trigger_release, suppress=False
        )
        # Monitor modifier releases for hold mode behavior
        for mod in self._modifiers:
            keyboard.on_release_key(mod, self._on_modifier_release, suppress=False)
        self._registered = True

    def register_arrow_keys(
        self,
        on_up: Callable[[], None],
        on_down: Callable[[], None],
    ) -> None:
        """Register up/down arrow key handlers for format mode cycling."""
        self.unregister_arrow_keys()
        self._arrow_hooks.append(
            keyboard.on_press_key("up", lambda e: on_up(), suppress=False)
        )
        self._arrow_hooks.append(
            keyboard.on_press_key("down", lambda e: on_down(), suppress=False)
        )

    def unregister_arrow_keys(self) -> None:
        """Remove arrow key handlers."""
        for hook in self._arrow_hooks:
            keyboard.unhook(hook)
        self._arrow_hooks.clear()

    def unregister(self) -> None:
        """Remove all hotkey handlers."""
        if not self._registered:
            return
        keyboard.unhook_all()
        self._arrow_hooks.clear()
        self._registered = False
        self._recording = False
        self._toggle_active = False
        self._key_is_down = False
        self._press_time = None

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value

    def wait(self) -> None:
        """Block the current thread until Ctrl+C or program exit."""
        keyboard.wait()
