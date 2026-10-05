"""Small dictation indicator anchored under the text caret.

A pywebview window (transparent, frameless, never focused) holding a pill
with a mic glyph and five level bars. Follows the system light/dark theme.
"""

import ctypes
import ctypes.wintypes
import json
import threading
import time

from .caret import caret_rect, foreground_rect, place_below

INDICATOR_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  :root { --bg: rgba(243,243,243,.96); --fg: #1a1a1a; --accent: #0067c0;
          --border: rgba(0,0,0,.08); --error: #c42b1c; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: rgba(44,44,44,.96); --fg: #ffffff; --accent: #4cc2ff;
            --border: rgba(255,255,255,.08); --error: #ff99a4; } }
  html, body { margin: 0; background: transparent; overflow: hidden; user-select: none;
               font: 12px "Segoe UI Variable Text", "Segoe UI", sans-serif; }
  .pill { position: absolute; left: 4px; top: 4px; height: 26px; padding: 0 11px 0 9px;
          display: flex; align-items: center; gap: 7px; border-radius: 13px; background: var(--bg);
          color: var(--fg); border: 1px solid var(--border);
          box-shadow: 0 1px 4px rgba(0,0,0,.16); opacity: 0; transform: translateY(-2px);
          transition: opacity .12s ease, transform .12s ease; white-space: nowrap; }
  .pill.on { opacity: 1; transform: none; }
  .mic { width: 13px; height: 13px; color: var(--accent); flex: none; }
  .bars { display: flex; align-items: center; gap: 2px; height: 14px; }
  .bars i { display: block; width: 3px; height: 3px; border-radius: 2px; background: var(--accent);
            transition: height .06s linear; }
  .finishing .bars i { animation: pulse 1s ease-in-out infinite; height: 4px; }
  .finishing .bars i:nth-child(2) { animation-delay: .1s } .finishing .bars i:nth-child(3) { animation-delay: .2s }
  .finishing .bars i:nth-child(4) { animation-delay: .3s } .finishing .bars i:nth-child(5) { animation-delay: .4s }
  @keyframes pulse { 50% { opacity: .3 } }
  .msg { display: none; color: var(--error); }
  .error .bars { display: none } .error .msg { display: inline } .error .mic { color: var(--error) }
</style></head><body>
<div class="pill" id="pill">
  <svg class="mic" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a2.5 2.5 0 0 0-2.5 2.5v4a2.5 2.5 0 0 0 5 0v-4A2.5 2.5 0 0 0 8 1Zm-4.5 6a.5.5 0 0 0-1 0 5.5 5.5 0 0 0 5 5.48V14H6a.5.5 0 0 0 0 1h4a.5.5 0 0 0 0-1H8.5v-1.52a5.5 5.5 0 0 0 5-5.48.5.5 0 0 0-1 0 4.5 4.5 0 0 1-9 0Z"/></svg>
  <span class="bars"><i></i><i></i><i></i><i></i><i></i></span>
  <span class="msg" id="msg"></span>
</div>
<script>
  var pill = document.getElementById('pill'), bars = pill.querySelectorAll('.bars i');
  function show() { pill.className = 'pill on'; }
  function hide() { pill.className = 'pill'; }
  function setState(s) { pill.className = 'pill on ' + s; }
  function showError(m) { document.getElementById('msg').textContent = m; pill.className = 'pill on error'; }
  function updateLevels(levels) {
    for (var i = 0; i < bars.length; i++) {
      bars[i].style.height = Math.max(3, Math.min(14, 3 + (levels[i] || 0) / 0.05 * 11)) + 'px';
    }
  }
</script></body></html>
"""


class CaretIndicator:
    WIDTH = 92          # logical px, including the 4 px shadow margin each side
    HEIGHT = 34
    ERROR_WIDTH = 340
    GAP = 6
    BAR_COUNT = 5
    ERROR_SECONDS = 4.0

    def __init__(self):
        self._window = None
        self._hwnd = None
        self._visible = False
        self._width = self.WIDTH
        # Bumped by every show/hide: a delayed hide only acts if nothing has
        # happened since it was scheduled.
        self._generation = 0
        self._gen_lock = threading.Lock()

    def _bump(self) -> int:
        with self._gen_lock:
            self._generation += 1
            return self._generation

    # -- window plumbing -----------------------------------------------------------

    def set_window(self, window) -> None:
        self._window = window

    def apply_win32_styles(self) -> None:
        """Never activate, never appear in Alt+Tab, never catch clicks, and
        start hidden (pywebview shows transparent windows once on load)."""
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "ShuperWhisper Indicator")
        if not hwnd:
            print("WARNING: indicator window not found")
            return
        self._hwnd = hwnd
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT = 0x08000000, 0x00000080, 0x00000020
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT)
        if not self._visible:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE

    def _eval(self, js: str) -> None:
        if self._window:
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass

    @staticmethod
    def _monitor_for(point):
        """(work area, DPI scale) of the monitor containing ``point``."""
        user32 = ctypes.windll.user32

        class _MI(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.wintypes.RECT),
                        ("rcWork", ctypes.wintypes.RECT), ("dwFlags", ctypes.c_ulong)]

        hmon = user32.MonitorFromPoint(ctypes.wintypes.POINT(*point), 2)  # NEAREST
        info = _MI(cbSize=ctypes.sizeof(_MI))
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        rc = info.rcWork
        scale = 1.0
        try:
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))
            scale = dx.value / 96.0
        except Exception:
            pass
        return (rc.left, rc.top, rc.right, rc.bottom), scale

    def _move(self, x, y, w, h) -> None:
        SWP_NOACTIVATE, SWP_NOZORDER = 0x0010, 0x0004
        ctypes.windll.user32.SetWindowPos(self._hwnd, None, x, y, w, h,
                                          SWP_NOACTIVATE | SWP_NOZORDER)

    def reposition(self, use_uia: bool = False) -> None:
        """Sit just under the caret; fall back to the bottom of the window."""
        if not self._hwnd:
            return
        caret = caret_rect(use_uia=use_uia)
        if caret is None:
            window = foreground_rect()
            if window is None:
                return
            work, scale = self._monitor_for(((window[0] + window[2]) // 2, window[3]))
            w, h = int(self._width * scale), int(self.HEIGHT * scale)
            x = (window[0] + window[2] - w) // 2
            self._move(x, window[3] - h - int(24 * scale), w, h)
            return
        work, scale = self._monitor_for((caret[0], caret[3]))
        w, h = int(self._width * scale), int(self.HEIGHT * scale)
        x, y = place_below(caret, work, (w, h), int(self.GAP * scale))
        self._move(x, y, w, h)

    # -- public API ----------------------------------------------------------------

    def show(self) -> None:
        self._bump()
        self._visible = True
        self._width = self.WIDTH
        self._eval("show()")
        if self._hwnd:
            self.reposition(use_uia=True)
            ctypes.windll.user32.ShowWindow(self._hwnd, 8)  # SW_SHOWNOACTIVATE

    def set_state(self, state: str) -> None:
        self._eval(f"setState('{state}')")

    def show_error(self, message: str) -> None:
        generation = self._bump()
        self._visible = True
        self._width = self.ERROR_WIDTH
        self._eval(f"showError({json.dumps(message)})")
        if self._hwnd:
            self.reposition(use_uia=False)
            ctypes.windll.user32.ShowWindow(self._hwnd, 8)

        def _later():
            time.sleep(self.ERROR_SECONDS)
            if self._generation == generation:  # nothing newer is showing
                self.hide()
        threading.Thread(target=_later, daemon=True).start()

    def hide(self) -> None:
        generation = self._bump()
        self._visible = False
        self._eval("hide()")
        if self._hwnd:
            def _later():
                time.sleep(0.15)
                if self._generation == generation:
                    ctypes.windll.user32.ShowWindow(self._hwnd, 0)
            threading.Thread(target=_later, daemon=True).start()

    def update_levels(self, levels) -> None:
        if not self._visible:
            return
        self._eval("updateLevels([" + ",".join(f"{v:.4f}" for v in levels[:self.BAR_COUNT]) + "])")

    @property
    def is_visible(self) -> bool:
        return self._visible

    def destroy(self) -> None:
        self._visible = False
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
