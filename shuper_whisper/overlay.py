"""Floating recording overlay with CSS animations via pywebview."""

import ctypes
import ctypes.wintypes
import threading
from typing import Callable, Optional

from .config import FORMAT_MODE_LABELS, FORMAT_MODE_ORDER


# Win32 structures for multi-monitor detection
class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]

# Embedded HTML/CSS/JS for the overlay — no external files, no PyInstaller path issues
OVERLAY_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #010101;
    overflow: hidden;
    user-select: none;
    -webkit-app-region: no-drag;
  }

  .overlay-root {
    opacity: 1;
    transition: opacity 0.15s ease;
  }
  .overlay-root.hidden { opacity: 0; pointer-events: none; }

  .container {
    width: 244px;
    margin: 8px 18px;
    position: relative;
  }

  /* Pill wrapper — clips the rotating glow to the border shape */
  .pill-wrapper {
    position: relative;
    width: 244px;
    height: 44px;
    border-radius: 22px;
    overflow: hidden;
  }

  /* Animated conic gradient glow (processing state) */
  .pill-glow {
    position: absolute;
    top: -100%;
    left: -100%;
    width: 300%;
    height: 300%;
    background: conic-gradient(
      transparent 0deg,
      transparent 200deg,
      var(--accent-dim, rgba(255,68,102,0.25)) 280deg,
      var(--accent, #ff4466) 350deg,
      transparent 360deg
    );
    animation: spin 2s linear infinite;
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 1;
  }

  .pill-glow.active { opacity: 1; }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Static white border (recording state) */
  .pill-border-static {
    position: absolute;
    inset: 0;
    border-radius: 22px;
    border: 2px solid #ffffff;
    z-index: 2;
    pointer-events: none;
    transition: opacity 0.2s ease;
  }

  /* Pill content — covers center, leaving only the 2px border ring visible */
  .pill-content {
    position: absolute;
    inset: 2px;
    border-radius: 20px;
    background: var(--bg, #1a1a2e);
    z-index: 3;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  /* Outer glow shadow during processing */
  .pill-wrapper.processing {
    filter: drop-shadow(0 0 8px var(--accent-dim, rgba(255,68,102,0.25)));
  }

  /* Waveform bars */
  .waveform {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 22px;
  }

  .bar {
    width: 4px;
    border-radius: 2px;
    background: var(--bar-idle, #3f1122);
    transition: height 50ms ease-out, background-color 100ms ease;
    min-height: 4px;
  }

  .bar.active { background: var(--accent, #ff4466); }

  /* Processing text */
  .processing-text {
    display: none;
    color: #cccccc;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.5px;
  }

  .processing-text.visible {
    display: block;
    animation: shimmer 1.5s ease-in-out infinite;
  }

  @keyframes shimmer {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
  }

  /* Format mode display */
  .format-row {
    display: none;
    justify-content: center;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    height: 20px;
  }

  .format-row.visible { display: flex; }

  .format-arrow {
    color: #888888;
    font-size: 10px;
    opacity: 0.6;
  }

  .format-label {
    color: #cccccc;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 12px;
    font-weight: 600;
    min-width: 120px;
    text-align: center;
  }
</style>
</head>
<body>
  <div class="overlay-root hidden" id="root">
    <div class="container">
      <div class="pill-wrapper" id="pill-wrapper">
        <div class="pill-glow" id="glow"></div>
        <div class="pill-border-static" id="border-static"></div>
        <div class="pill-content" id="content">
          <div class="waveform" id="waveform"></div>
          <div class="processing-text" id="proc-text">Processing...</div>
        </div>
      </div>
      <div class="format-row" id="format-row">
        <span class="format-arrow">&#9650;</span>
        <span class="format-label" id="format-label">Normal</span>
        <span class="format-arrow">&#9660;</span>
      </div>
    </div>
  </div>

  <script>
    var BAR_COUNT = 14;
    var waveform = document.getElementById('waveform');
    for (var i = 0; i < BAR_COUNT; i++) {
      var bar = document.createElement('div');
      bar.className = 'bar';
      bar.style.height = '4px';
      waveform.appendChild(bar);
    }

    var root = document.getElementById('root');
    var glow = document.getElementById('glow');
    var pillWrapper = document.getElementById('pill-wrapper');
    var borderStatic = document.getElementById('border-static');
    var procText = document.getElementById('proc-text');
    var formatRow = document.getElementById('format-row');
    var formatLabel = document.getElementById('format-label');
    var bars = waveform.children;

    function showOverlay(mode, fmtLabel) {
      root.classList.remove('hidden');
      waveform.style.display = 'flex';
      procText.classList.remove('visible');
      glow.classList.remove('active');
      pillWrapper.classList.remove('processing');
      borderStatic.style.opacity = '1';
      if (mode === 'toggle') {
        formatRow.classList.add('visible');
      } else {
        formatRow.classList.remove('visible');
      }
      formatLabel.textContent = fmtLabel || 'Normal';
      for (var i = 0; i < bars.length; i++) {
        bars[i].style.height = '4px';
        bars[i].classList.remove('active');
      }
    }

    function showProcessing() {
      waveform.style.display = 'none';
      procText.classList.add('visible');
      glow.classList.add('active');
      pillWrapper.classList.add('processing');
      borderStatic.style.opacity = '0';
      formatRow.classList.remove('visible');
    }

    function hideOverlay() {
      root.classList.add('hidden');
      glow.classList.remove('active');
      pillWrapper.classList.remove('processing');
    }

    function updateLevels(levels) {
      for (var i = 0; i < bars.length && i < levels.length; i++) {
        var norm = Math.min(1.0, levels[i] / 0.05);
        var h = Math.max(4, norm * 22);
        bars[i].style.height = h + 'px';
        if (norm > 0.1) {
          bars[i].classList.add('active');
        } else {
          bars[i].classList.remove('active');
        }
      }
    }

    function setFormatMode(label) {
      formatLabel.textContent = label;
    }

    function setColors(accent, bg) {
      var r = parseInt(accent.slice(1,3), 16);
      var g = parseInt(accent.slice(3,5), 16);
      var b = parseInt(accent.slice(5,7), 16);
      root.style.setProperty('--accent', accent);
      root.style.setProperty('--accent-dim', 'rgba(' + r + ',' + g + ',' + b + ',0.25)');
      root.style.setProperty('--bar-idle', 'rgba(' + r + ',' + g + ',' + b + ',0.25)');
      root.style.setProperty('--bg', bg);
    }
  </script>
</body>
</html>
"""


class RecordingOverlay:
    """Floating overlay using pywebview with CSS animations.

    Uses Win32 LWA_COLORKEY for window transparency (#010101 becomes transparent).
    All public methods are thread-safe (evaluate_js posts to the GUI thread).
    """

    # Layout constants (kept for API compatibility with tests and app.py)
    WINDOW_W = 280
    WINDOW_H_HOLD = 60
    WINDOW_H_TOGGLE = 92
    BAR_COUNT = 14

    def __init__(self, position: str = "top_center",
                 accent_color: str = "#ff4466",
                 bg_color: str = "#1a1a2e"):
        self._position = position
        self._accent_color = accent_color
        self._bg_color = bg_color
        self._visible = False
        self._mode = "hold"
        self._format_mode = "normal"
        self._state = "recording"
        self._window = None  # pywebview window, set by tray.py via set_window()
        self._hwnd = None
        self._on_format_change: Optional[Callable[[str], None]] = None
        self._ready = threading.Event()

    @staticmethod
    def _hex_alpha(hex_color: str, alpha: float) -> str:
        """Blend a hex color toward black by alpha."""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r = int(r * alpha)
        g = int(g * alpha)
        b = int(b * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    def set_window(self, window) -> None:
        """Set the pywebview window reference. Called by tray.py after creation."""
        self._window = window
        self._ready.set()

    def apply_win32_styles(self) -> None:
        """Apply Win32 transparency and no-activate styles.

        Called after the pywebview window is fully loaded.
        """
        try:
            # Find the HWND by window title
            hwnd = ctypes.windll.user32.FindWindowW(None, "ShuperWhisper Overlay")

            if not hwnd:
                # Fallback: enumerate windows by PID
                import os
                pid = os.getpid()
                found = []

                @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                def enum_cb(h, _):
                    proc_id = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(
                        h, ctypes.byref(proc_id)
                    )
                    if proc_id.value == pid:
                        length = ctypes.windll.user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(h, buf, length + 1)
                            if "Overlay" in buf.value:
                                found.append(h)
                    return True

                ctypes.windll.user32.EnumWindows(enum_cb, 0)
                hwnd = found[0] if found else None

            if not hwnd:
                print("WARNING: Could not find overlay HWND, transparency unavailable")
                return

            self._hwnd = hwnd

            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_LAYERED = 0x00080000
            LWA_COLORKEY = 0x00000001

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_LAYERED,
            )

            # Set #010101 as the transparent color key (COLORREF is BGR)
            color_key = 0x00010101
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd, color_key, 0, LWA_COLORKEY,
            )

            # Position the window
            self._position_window()

        except Exception as e:
            print(f"WARNING: Win32 overlay styles failed: {e}")

    @staticmethod
    def _get_active_monitor_work_area() -> tuple[int, int, int, int]:
        """Get the work area of the monitor containing the foreground window.

        Returns (x, y, width, height) of the monitor's work area.
        Falls back to the primary monitor if no foreground window exists.
        """
        user32 = ctypes.windll.user32
        MONITOR_DEFAULTTOPRIMARY = 0x00000001

        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd:
            hmon = user32.MonitorFromWindow(fg_hwnd, MONITOR_DEFAULTTOPRIMARY)
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                rc = mi.rcWork
                return (rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)

        # Fallback: primary monitor
        return (
            0,
            0,
            user32.GetSystemMetrics(0),
            user32.GetSystemMetrics(1),
        )

    def _position_window(self) -> None:
        """Position overlay on the monitor containing the focused window."""
        if not self._hwnd:
            return

        mon_x, mon_y, mon_w, mon_h = self._get_active_monitor_work_area()

        w = self.WINDOW_W
        h = self.WINDOW_H_TOGGLE if self._mode == "toggle" else self.WINDOW_H_HOLD
        x = mon_x + (mon_w - w) // 2

        positions = {
            "top_center": mon_y + 80,
            "center": mon_y + (mon_h - h) // 2,
            "bottom_center": mon_y + mon_h - h - 100,
        }
        y = positions.get(self._position, mon_y + 80)

        SWP_NOACTIVATE = 0x0010
        SWP_NOZORDER = 0x0004
        ctypes.windll.user32.SetWindowPos(
            self._hwnd, None, x, y, w, h, SWP_NOACTIVATE | SWP_NOZORDER,
        )

    def _eval(self, js: str) -> None:
        """Thread-safe evaluate_js wrapper. No-op if window not set."""
        if self._window:
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass  # Window may be closing or not ready

    def start(self) -> None:
        """No-op for API compatibility. Window is created by tray.py."""
        pass

    def show(self, mode: str = "hold", format_mode: str = "normal") -> None:
        """Show the overlay. Thread-safe."""
        self._mode = mode
        self._format_mode = format_mode
        self._state = "recording"
        self._visible = True

        label = FORMAT_MODE_LABELS.get(format_mode, "Normal")
        self._eval(f"showOverlay('{mode}', '{label}')")

        # Show the pywebview window without stealing focus
        if self._hwnd:
            SW_SHOWNOACTIVATE = 8
            ctypes.windll.user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            self._position_window()

    def show_processing(self) -> None:
        """Switch overlay to processing state. Thread-safe."""
        if not self._visible:
            return
        self._state = "processing"
        self._eval("showProcessing()")

    def hide(self) -> None:
        """Hide the overlay. Thread-safe."""
        self._visible = False
        self._state = "recording"
        self._eval("hideOverlay()")

        # Hide window at Win32 level after CSS fade
        if self._hwnd:
            def _delayed_hide():
                import time
                time.sleep(0.2)
                if not self._visible:
                    ctypes.windll.user32.ShowWindow(self._hwnd, 0)  # SW_HIDE
            threading.Thread(target=_delayed_hide, daemon=True).start()

    def update_levels(self, levels: list[float]) -> None:
        """Update waveform levels. Thread-safe."""
        if not self._visible or self._state != "recording":
            return
        js_arr = "[" + ",".join(f"{l:.4f}" for l in levels[:self.BAR_COUNT]) + "]"
        self._eval(f"updateLevels({js_arr})")

    def cycle_format_mode(self, direction: int) -> str:
        """Cycle format mode by direction (-1=up, +1=down). Returns new mode."""
        try:
            idx = FORMAT_MODE_ORDER.index(self._format_mode)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(FORMAT_MODE_ORDER)
        self._format_mode = FORMAT_MODE_ORDER[idx]

        label = FORMAT_MODE_LABELS.get(self._format_mode, "Normal")
        self._eval(f"setFormatMode('{label}')")

        if self._on_format_change:
            self._on_format_change(self._format_mode)
        return self._format_mode

    def set_on_format_change(self, callback: Callable[[str], None]) -> None:
        self._on_format_change = callback

    @property
    def format_mode(self) -> str:
        return self._format_mode

    @property
    def is_visible(self) -> bool:
        return self._visible

    def set_position(self, position: str) -> None:
        self._position = position

    def set_colors(self, accent_color: str, bg_color: str) -> None:
        """Update overlay colors. Applied immediately if window is ready."""
        self._accent_color = accent_color
        self._bg_color = bg_color
        self._eval(f"setColors('{accent_color}', '{bg_color}')")

    def destroy(self) -> None:
        """Clean up the overlay."""
        self._visible = False
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
