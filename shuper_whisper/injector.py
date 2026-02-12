"""Text injection via clipboard and simulated paste."""

import time

import keyboard
import pyperclip

from .smart_text import process_text


class TextInjector:
    """Injects transcribed text into the currently focused text field."""

    def __init__(
        self,
        paste_delay: float = 0.1,
        smart_spacing: bool = True,
        bullet_mode: bool = False,
        email_mode: bool = False,
    ):
        self._paste_delay = paste_delay
        self.smart_spacing = smart_spacing
        self.bullet_mode = bullet_mode
        self.email_mode = email_mode

    def _probe_context(self) -> str | None:
        """Try to read text preceding the cursor in the active field.

        Uses Shift+Home to select to start of line, copies, then restores.
        Returns None if probing fails.
        """
        if not (self.smart_spacing or self.bullet_mode):
            return None

        try:
            # Save current clipboard
            original_clip = pyperclip.paste()

            # Select from cursor to start of line and copy
            pyperclip.copy("")
            time.sleep(0.02)
            keyboard.send("shift+home")
            time.sleep(0.05)
            keyboard.send("ctrl+c")
            time.sleep(0.05)

            context = pyperclip.paste()

            # Deselect (move cursor back to original position)
            keyboard.send("right")
            time.sleep(0.02)

            # Restore original clipboard
            pyperclip.copy(original_clip)

            return context if context else None
        except Exception:
            return None

    def inject(self, text: str) -> None:
        """Process and inject transcribed text into the focused field.

        Probes context if smart features are enabled, then applies
        smart spacing/bullet/email formatting before pasting.

        Args:
            text: The transcribed text to inject.
        """
        if not text:
            return

        has_smart_features = self.smart_spacing or self.bullet_mode or self.email_mode

        if has_smart_features:
            context = self._probe_context()
            text = process_text(
                context=context,
                text=text,
                smart_spacing=self.smart_spacing,
                bullet_mode=self.bullet_mode,
                email_mode=self.email_mode,
            )

        pyperclip.copy(text)
        time.sleep(self._paste_delay)
        keyboard.send("ctrl+v")
