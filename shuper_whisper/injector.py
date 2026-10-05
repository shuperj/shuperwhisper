"""Types text at the caret of whatever control has focus.

Uses SendInput unicode keystrokes, so the clipboard is never touched. Context
for spacing/capitalisation comes from UI Automation, falling back to what we
last typed into the same window.
"""

from typing import Callable, Optional

from . import uia
from ._win32_keys import send_text, user32, wait_for_modifiers_released
from .text_rules import join

_HISTORY_CHARS = 200


class TextInjector:
    def __init__(
        self,
        send: Callable[..., None] = send_text,
        read_context: Callable[[], Optional[str]] = uia.text_before_caret,
        foreground: Callable[[], int] = user32.GetForegroundWindow,
        wait_modifiers: Callable[[], bool] = wait_for_modifiers_released,
    ):
        self._send = send
        self._read_context = read_context
        self._foreground = foreground
        self._wait_modifiers = wait_modifiers
        self._last_hwnd: Optional[int] = None
        self._last_typed = ""

    def context(self) -> Optional[str]:
        before = self._read_context()
        if before is not None:
            return before
        if self._last_typed and self._foreground() == self._last_hwnd:
            return self._last_typed
        return None

    def inject(self, text: str) -> str:
        """Type cleaned ``text`` at the caret. Returns exactly what was typed."""
        if not text:
            return ""
        self._wait_modifiers()
        typed = join(text, self.context())
        self._send(typed)
        hwnd = self._foreground()
        if hwnd != self._last_hwnd:
            self._last_hwnd, self._last_typed = hwnd, ""
        self._last_typed = (self._last_typed + typed)[-_HISTORY_CHARS:]
        return typed
