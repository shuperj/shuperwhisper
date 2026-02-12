"""System tray controller using pystray."""

import threading
from typing import Optional

import pystray
from PIL import Image, ImageDraw

from .app import (
    STATE_IDLE,
    STATE_LOADING,
    STATE_PROCESSING,
    STATE_RECORDING,
    ShuperWhisperApp,
)
from .autostart import disable_autostart, enable_autostart, is_autostart_enabled
from .config import AppConfig, load_config, save_config

# Icon colors for each state
_COLORS = {
    STATE_IDLE: "#CCCCCC",
    STATE_RECORDING: "#FF3333",
    STATE_PROCESSING: "#FFAA00",
    STATE_LOADING: "#6699FF",
}


def _make_icon(color: str, size: int = 64) -> Image.Image:
    """Generate a simple circular icon with the given color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return img


class TrayController:
    """Manages the system tray icon and bridges it to the app."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.app = ShuperWhisperApp(config)
        self.app.set_state_callback(self._on_state_change)
        self._icon: Optional[pystray.Icon] = None
        self._current_state = STATE_IDLE

    def _on_state_change(self, state: str) -> None:
        self._current_state = state
        if self._icon is not None:
            self._icon.icon = _make_icon(_COLORS.get(state, _COLORS[STATE_IDLE]))
            self._icon.title = f"ShuperWhisper - {state.capitalize()}"

    def _open_settings(self, icon, item) -> None:
        """Open the settings dialog in a separate thread."""
        from .settings_ui import open_settings_dialog

        def _on_save(new_config: AppConfig):
            self.config = new_config
            save_config(new_config)
            if new_config.autostart:
                enable_autostart()
            else:
                disable_autostart()
            self.app.reload_config(new_config)

        threading.Thread(
            target=open_settings_dialog,
            args=(self.config, _on_save),
            daemon=True,
        ).start()

    def _toggle_autostart(self, icon, item) -> None:
        if is_autostart_enabled():
            disable_autostart()
            self.config.autostart = False
        else:
            enable_autostart()
            self.config.autostart = True
        save_config(self.config)

    def _quit(self, icon, item) -> None:
        self.app.shutdown()
        icon.stop()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Settings...", self._open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start with Windows",
                self._toggle_autostart,
                checked=lambda item: is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _setup(self, icon: pystray.Icon) -> None:
        """Called by pystray after the icon is ready. Starts the app in a background thread."""
        icon.visible = True

        def _start_app():
            self.app.start()

        threading.Thread(target=_start_app, daemon=True).start()

    def run(self) -> None:
        """Create the tray icon and run the event loop. Blocks until quit."""
        self._icon = pystray.Icon(
            name="ShuperWhisper",
            icon=_make_icon(_COLORS[STATE_IDLE]),
            title="ShuperWhisper - Starting...",
            menu=self._build_menu(),
        )
        self._icon.run(setup=self._setup)
