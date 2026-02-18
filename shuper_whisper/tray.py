"""System tray controller using pystray."""

import os
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional

import pystray
import webview
from PIL import Image, ImageDraw

from .app import (
    STATE_IDLE,
    STATE_LOADING,
    STATE_PROCESSING,
    STATE_RECORDING,
    ShuperWhisperApp,
)
from .bridge import WindowAPI
from .config import AppConfig, load_config
from .overlay import OVERLAY_HTML

# Icon colors for each state
_COLORS = {
    STATE_IDLE: "#CCCCCC",
    STATE_RECORDING: "#FF3333",
    STATE_PROCESSING: "#FFAA00",
    STATE_LOADING: "#6699FF",
}

# Resolve the path to the React build (handles both dev and PyInstaller)
if getattr(sys, 'frozen', False):
    _DIST_DIR = os.path.join(sys._MEIPASS, 'shuper_whisper', 'ui', 'dist')
else:
    _DIST_DIR = os.path.join(os.path.dirname(__file__), 'ui', 'dist')

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


def _make_icon(color: str, size: int = 64) -> Image.Image:
    """Generate a simple circular icon with the given color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return img


class TrayController:
    """Manages the system tray icon and bridges it to the app.

    Architecture: The main thread runs pywebview.start() permanently.
    The overlay window is created at startup (hidden) and persists for the
    lifetime of the app. Settings windows are created on demand.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.app = ShuperWhisperApp(config)
        self.app.set_state_callback(self._on_state_change)
        self._icon: Optional[pystray.Icon] = None
        self._current_state = STATE_IDLE
        self._overlay_window = None

        # Shared API instance — app reference wired here, window set per-settings-open
        self._api = WindowAPI()
        self._api.set_app_instance(self.app)

    def _on_state_change(self, state: str) -> None:
        self._current_state = state
        if self._icon is not None:
            self._icon.icon = _make_icon(_COLORS.get(state, _COLORS[STATE_IDLE]))
            self._icon.title = f"ShuperWhisper - {state.capitalize()}"

    def _open_settings(self, icon, item) -> None:
        """Create a settings webview window from the tray thread."""
        dist_index = os.path.join(_DIST_DIR, 'index.html')

        if not os.path.exists(dist_index):
            print(f"WARNING: React build not found at {dist_index}")
            return

        port = _ensure_static_server()

        api = WindowAPI()
        api.set_app_instance(self.app)

        window = webview.create_window(
            'ShuperWhisper Settings',
            url=f'http://127.0.0.1:{port}/',
            width=500,
            height=640,
            resizable=False,
            frameless=False,
            js_api=api,
        )

        api._window = window

    def _quit(self, icon, item) -> None:
        self.app.shutdown()
        icon.stop()
        # Destroy all webview windows to let webview.start() return
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Settings...", self._open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _setup(self, icon: pystray.Icon) -> None:
        """Called by pystray after the icon is ready. Starts the app in a background thread."""
        icon.visible = True

        def _start_app():
            self.app.start()

        threading.Thread(target=_start_app, daemon=True).start()

    def _on_overlay_loaded(self) -> None:
        """Called when the overlay webview DOM is fully loaded."""
        # Apply Win32 styles for transparency and non-focusable behavior
        self.app.overlay.apply_win32_styles()

        # Send initial colors
        self.app.overlay.set_colors(
            self.config.accent_color, self.config.bg_color,
        )

    def run(self) -> None:
        """Create the tray icon and run the event loop.

        pystray runs in a background thread. The main thread runs pywebview.start()
        permanently, with the overlay window kept alive for the app's lifetime.
        """
        self._icon = pystray.Icon(
            name="ShuperWhisper",
            icon=_make_icon(_COLORS[STATE_IDLE]),
            title="ShuperWhisper - Starting...",
            menu=self._build_menu(),
        )

        # Run pystray in a background thread
        threading.Thread(
            target=self._icon.run,
            kwargs={"setup": self._setup},
            daemon=True,
        ).start()

        # Create the overlay pywebview window (hidden, frameless, always on top)
        self._overlay_window = webview.create_window(
            'ShuperWhisper Overlay',
            html=OVERLAY_HTML,
            width=280,
            height=92,
            frameless=True,
            hidden=True,
            on_top=True,
        )

        # Wire the overlay window to the app's overlay controller
        self.app.overlay.set_window(self._overlay_window)

        # Register loaded event for Win32 style application
        self._overlay_window.events.loaded += self._on_overlay_loaded

        # Start pywebview event loop on the main thread (blocks forever).
        # The overlay window persists; settings windows come and go.
        # When all windows are destroyed (via _quit), start() returns.
        webview.start()
