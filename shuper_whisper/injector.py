"""Text injection via clipboard and simulated paste."""

import time

import keyboard
import pyperclip


class TextInjector:
    """Injects transcribed text into the currently focused text field."""

    def __init__(self, paste_delay: float = 0.1):
        self._paste_delay = paste_delay

    def inject(self, text: str) -> None:
        """Copy text to clipboard and simulate Ctrl+V to paste it.

        Args:
            text: The transcribed text to inject.
        """
        if not text:
            return
        pyperclip.copy(text)
        time.sleep(self._paste_delay)
        keyboard.send("ctrl+v")
