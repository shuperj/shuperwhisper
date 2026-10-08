"""System tray controller using pystray."""

import ctypes
import os
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional

import pystray
import webview
from PIL import Image, ImageDraw

from .app import (
    STATE_ERROR,
    STATE_IDLE,
    STATE_LOADING,
    STATE_PROCESSING,
    STATE_RECORDING,
    ShuperWhisperApp,
)
from . import autostart, system_theme
from .bridge import WindowAPI
from .config import AppConfig, load_config

# Icon colors for each state
_COLORS = {
    STATE_IDLE: "#CCCCCC",
    STATE_LOADING: "#6699FF",
    STATE_ERROR: "#E81123",  # red means something is wrong, nothing else
}
_EFFICIENT = "#6CCB5F"  # efficiency mode: green the whole time


def _icon_color(state: str, efficient: bool) -> str:
    """Error red and loading blue win; then efficiency green; dictating is the
    Windows accent colour (like the pill); idle is grey."""
    if state in (STATE_ERROR, STATE_LOADING):
        return _COLORS[state]
    if efficient:
        return _EFFICIENT
    if state in (STATE_RECORDING, STATE_PROCESSING):
        accents = system_theme.accent_colors()
        return accents["dark"] if system_theme.taskbar_uses_dark() else accents["light"]
    return _COLORS[STATE_IDLE]

# Resolve the path to the React build (handles both dev and PyInstaller)
if getattr(sys, 'frozen', False):
    _DIST_DIR = os.path.join(sys._MEIPASS, 'shuper_whisper', 'ui', 'dist')
    _LOGO_MASK = os.path.join(sys._MEIPASS, 'shuper_whisper', 'assets', 'logo_mask.png')
else:
    _DIST_DIR = os.path.join(os.path.dirname(__file__), 'ui', 'dist')
    _LOGO_MASK = os.path.join(os.path.dirname(__file__), 'assets', 'logo_mask.png')

# Minimal HTTP server for serving React static files.
# WebView2 blocks ES module scripts over file:// protocol, so we need HTTP.
# Windows registry can map .js to text/plain, which blocks ES modules —
# so we use a custom handler with explicit MIME types.
_static_server_port: Optional[int] = None


class _StaticHandler(SimpleHTTPRequestHandler):
    """Serve React build with correct MIME types (Windows registry can be wrong)."""

    _MIME_TYPES = {
        '.js': 'application/javascript',
        '.mjs': 'application/javascript',
        '.css': 'text/css',
        '.html': 'text/html',
        '.json': 'application/json',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.ico': 'image/x-icon',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_DIST_DIR, **kwargs)

    def guess_type(self, path):
        _, ext = os.path.splitext(path)
        return self._MIME_TYPES.get(ext.lower(), super().guess_type(path))

    def end_headers(self):
        # Prevent WebView2 from caching assets (stale CSS/JS across rebuilds)
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        pass  # Silence per-request logging


def _ensure_static_server() -> int:
    """Start a localhost HTTP server for the React build (once, lazily)."""
    global _static_server_port
    if _static_server_port is not None:
        return _static_server_port

    server = HTTPServer(('127.0.0.1', 0), _StaticHandler)
    _static_server_port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return _static_server_port


_logo_mask: Optional[Image.Image] = None


def _make_icon(color: str, size: int = 64) -> Image.Image:
    """The ShuperWhisper logo (no background) in the given colour; a plain
    circle if the logo file is missing. The mask comes from
    packaging/make_logo_assets.py."""
    global _logo_mask
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if _logo_mask is None and os.path.exists(_LOGO_MASK):
        _logo_mask = Image.open(_LOGO_MASK).convert("L")
    if _logo_mask is None:
        margin = 4
        ImageDraw.Draw(img).ellipse([margin, margin, size - margin, size - margin], fill=color)
        return img
    # The logo is wide: fit its width, centre it vertically.
    width = size
    height = round(_logo_mask.height * width / _logo_mask.width)
    mask = _logo_mask.resize((width, height), Image.LANCZOS)
    logo = Image.new("RGBA", (width, height), color)
    logo.putalpha(mask)
    img.paste(logo, (0, (size - height) // 2))
    return img


class TrayController:
    """Manages the system tray icon and bridges it to the app.

    Architecture: The main thread runs pywebview.start() permanently.
    A hidden host window keeps pywebview's loop alive for the lifetime of the
    app. Settings windows are created on demand.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.app = ShuperWhisperApp(config)
        self.app.set_state_callback(self._on_state_change)
        self._icon: Optional[pystray.Icon] = None
        self._current_state = STATE_IDLE
        self._host_window = None

        # Shared API instance — app reference wired here, window set per-settings-open
        self._api = WindowAPI()
        self._api.set_app_instance(self.app)

    def _on_state_change(self, state: str) -> None:
        self._current_state = state
        if self._icon is not None:
            self._icon.icon = _make_icon(_icon_color(state, self.app.efficient))
            words = {STATE_RECORDING: "Dictating", STATE_PROCESSING: "Finishing"}
            detail = self.app.error if state == STATE_ERROR and self.app.error else                 words.get(state, state.capitalize())
            if self.app.efficient and state != STATE_ERROR:
                detail += f" (efficiency mode: {self.app.efficiency_reason})"
            # Windows caps tray tooltips at 127 characters.
            self._icon.title = f"ShuperWhisper - {detail}"[:127]

    def _open_settings(self, icon, item) -> None:
        """Open (or focus) the settings window."""
        dist_index = os.path.join(_DIST_DIR, 'index.html')
        if not os.path.exists(dist_index):
            print(f"WARNING: React build not found at {dist_index}")
            return
        existing = [w for w in webview.windows if w.title == 'ShuperWhisper Settings']
        if existing:
            existing[0].restore()
            existing[0].show()
            return

        port = _ensure_static_server()
        api = WindowAPI()
        api.set_app_instance(self.app)
        dark = system_theme.apps_use_dark()
        window = webview.create_window(
            'ShuperWhisper Settings',
            url=f'http://127.0.0.1:{port}/',
            width=560,
            height=700,
            min_size=(460, 520),
            resizable=True,
            background_color='#202020' if dark else '#f3f3f3',
            js_api=api,
        )
        api._window = window

        def _style():
            hwnd = ctypes.windll.user32.FindWindowW(None, 'ShuperWhisper Settings')
            if hwnd:
                system_theme.apply_window_theme(hwnd, dark)
        window.events.shown += _style
        window.events.closed += api.stop_mic_test

    def _toggle_autostart(self, icon, item) -> None:
        new_state = autostart.toggle()
        print(f"[tray] Autostart {'enabled' if new_state else 'disabled'}", flush=True)

    def _quit(self, icon, item) -> None:
        self.app.shutdown()
        icon.stop()
        # Destroy all webview windows to let webview.start() return
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass

    def _efficiency_item(self, setting: str, label: str) -> pystray.MenuItem:
        def _choose(icon, item):
            self.app.set_efficiency(setting, on_done=icon.update_menu)
        return pystray.MenuItem(label, _choose, radio=True,
                                checked=lambda item: self.app.config.efficiency == setting)

    def _build_menu(self) -> pystray.Menu:
        def _efficiency_title(item) -> str:
            return f"Efficiency mode: {'on' if self.app.efficient else 'off'}"
        return pystray.Menu(
            pystray.MenuItem("Settings...", self._open_settings),
            pystray.MenuItem(_efficiency_title, pystray.Menu(
                self._efficiency_item("auto", "Automatic (when a game is running)"),
                self._efficiency_item("on", "On"),
                self._efficiency_item("off", "Off"),
            )),
            pystray.MenuItem(
                "Start with Windows",
                self._toggle_autostart,
                checked=lambda item: autostart.is_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _setup(self, icon: pystray.Icon) -> None:
        """Called by pystray after the icon is ready. Starts the app in a background thread."""
        print("[tray] _setup called, icon ready", flush=True)
        icon.visible = True

        # start() never raises; failures show as the error state.
        threading.Thread(target=self.app.start, daemon=True).start()
        if "--settings" in sys.argv:  # open Settings straight away
            self._open_settings(icon, None)

    def run(self) -> None:
        """Create the tray icon and run the event loop.

        pystray runs in a background thread. The main thread runs pywebview.start()
        permanently, with a hidden host window kept alive for the app's lifetime.
        """
        self._icon = pystray.Icon(
            name="ShuperWhisper",
            icon=_make_icon(_icon_color(STATE_IDLE, self.app.efficient)),
            title="ShuperWhisper - Starting...",
            menu=self._build_menu(),
        )

        # Run pystray in a background thread
        threading.Thread(
            target=self._icon.run,
            kwargs={"setup": self._setup},
            daemon=True,
        ).start()

        # pywebview needs a window to run its loop; this hidden one lives for
        # the whole session while settings windows come and go. (The dictation
        # indicator is a native window of its own, see overlay.py.)
        self._host_window = webview.create_window(
            'ShuperWhisper', html='<html></html>', width=1, height=1,
            frameless=True, hidden=True, focus=False)

        # Blocks until every window is destroyed (via _quit).
        webview.start()
