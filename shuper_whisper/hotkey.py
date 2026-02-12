"""Global hotkey management using the keyboard library."""

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
    """Manages global hotkey registration with hold-to-record semantics.

    Args:
        hotkey_str: Hotkey combination string (e.g. "ctrl+shift+space").
        on_start: Called when the hotkey is pressed (recording should begin).
        on_stop: Called when the hotkey is released (recording should end).
    """

    def __init__(
        self,
        hotkey_str: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
    ):
        self._hotkey_str = hotkey_str
        self._on_start = on_start
        self._on_stop = on_stop
        self._modifiers, self._trigger_key = parse_hotkey(hotkey_str)
        self._held = False
        self._registered = False

    def _modifiers_pressed(self) -> bool:
        """Check if all required modifier keys are currently held."""
        return all(keyboard.is_pressed(mod) for mod in self._modifiers)

    def _on_trigger_press(self, event) -> None:
        if self._modifiers_pressed() and not self._held:
            self._held = True
            self._on_start()

    def _on_trigger_release(self, event) -> None:
        if self._held:
            self._held = False
            self._on_stop()

    def _on_modifier_release(self, event) -> None:
        if self._held:
            self._held = False
            self._on_stop()

    def register(self) -> None:
        """Register the hotkey handlers. Call once after setup."""
        if self._registered:
            return
        keyboard.on_press_key(self._trigger_key, self._on_trigger_press, suppress=False)
        keyboard.on_release_key(
            self._trigger_key, self._on_trigger_release, suppress=False
        )
        for mod in self._modifiers:
            keyboard.on_release_key(mod, self._on_modifier_release, suppress=False)
        self._registered = True

    def unregister(self) -> None:
        """Remove all hotkey handlers."""
        if not self._registered:
            return
        keyboard.unhook_all()
        self._registered = False
        self._held = False

    def wait(self) -> None:
        """Block the current thread until Ctrl+C or program exit."""
        keyboard.wait()
