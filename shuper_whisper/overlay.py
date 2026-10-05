"""Small dictation indicator: a pill with a mic glyph and level bars.

Drawn with PIL and shown in a native layered window (per-pixel alpha via
UpdateLayeredWindow), so it's truly transparent around the pill in every
app, never takes focus, and never catches clicks. It's placed under the text
caret when dictation starts and stays put; it only moves if dictation
continues in a different field.
"""

import ctypes
import ctypes.wintypes as wt
import os
import threading
import time
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import system_theme
from .caret import caret_rect, foreground_rect, place_below

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = (wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
user32.CreateWindowExW.restype = wt.HWND
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = (wt.HWND, wt.HDC)
user32.SetWindowPos.argtypes = (wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT)
user32.ShowWindow.argtypes = (wt.HWND, ctypes.c_int)
user32.PostMessageW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.GetMessageW.argtypes = (ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
gdi32.CreateCompatibleDC.argtypes = (wt.HDC,)
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateDIBSection.argtypes = (wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wt.HANDLE, wt.DWORD)
gdi32.CreateDIBSection.restype = wt.HBITMAP
user32.UpdateLayeredWindow.argtypes = (wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
                                       wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.c_void_p, wt.DWORD)
gdi32.SelectObject.argtypes = (wt.HDC, wt.HGDIOBJ)
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.DeleteObject.argtypes = (wt.HGDIOBJ,)
gdi32.DeleteDC.argtypes = (wt.HDC,)
kernel32.GetModuleHandleW.restype = wt.HMODULE


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", _WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


_WS_POPUP = 0x80000000
_WS_EX = 0x00080000 | 0x00000008 | 0x00000080 | 0x08000000 | 0x00000020  # LAYERED|TOPMOST|TOOLWINDOW|NOACTIVATE|TRANSPARENT
_HWND_TOPMOST = wt.HWND(-1)
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOACTIVATE, _SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0010, 0x0040
_SW_HIDE, _SW_SHOWNOACTIVATE = 0, 4
_WM_CLOSE, _WM_DESTROY = 0x0010, 0x0002
_ULW_ALPHA = 0x2

_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_MIC = "\ue720"  # Segoe Fluent Icons / Segoe MDL2 Assets "Microphone"


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(os.path.join(_FONTS, name), size)
        except OSError:
            continue
    return None


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


class Look:
    """Colours for one theme."""

    def __init__(self, dark: bool, accent: str):
        self.dark = dark
        self.bg = (44, 44, 44, 246) if dark else (249, 249, 249, 246)
        self.border = (255, 255, 255, 22) if dark else (0, 0, 0, 22)
        self.accent = _rgb(accent) + (255,)
        self.error = (255, 153, 164, 255) if dark else (196, 43, 28, 255)
        self.muted = (197, 197, 197, 255) if dark else (95, 95, 95, 255)

    @classmethod
    def system(cls) -> "Look":
        dark = system_theme.apps_use_dark()
        accents = system_theme.accent_colors()
        return cls(dark, accents["dark"] if dark else accents["light"])


def render(look: Look, scale: float, state: str = "listening", levels=(), message: str = "") -> Image.Image:
    """The indicator as an RGBA image, ``scale`` x the 1x layout.

    states: listening (mic + level bars), finishing (mic + dots), error (mic + message).
    """
    ss = 3  # supersampling for smooth edges
    k = scale * ss
    margin, height = 4 * k, 26 * k
    icon_font = _font(("SegoeIcons.ttf", "segmdl2.ttf"), int(13 * k))
    text_font = _font(("SegUIVar.ttf", "segoeui.ttf"), int(12 * k))
    if state == "error" and message and text_font:
        text_w = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(message, font=text_font)
        content_w = 13 * k + 7 * k + text_w
    else:
        content_w = 13 * k + 7 * k + (5 * 3 + 4 * 2) * k
    width = content_w + 20 * k
    w, h = int(width + 2 * margin), int(height + 2 * margin)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # soft shadow
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (margin, margin + 1 * k, margin + width, margin + height + 1 * k), radius=height / 2, fill=60)
    shadow = shadow.filter(ImageFilter.GaussianBlur(2.5 * k))
    img.paste((0, 0, 0, 255), (0, 0), shadow)

    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((margin, margin, margin + width, margin + height), radius=height / 2,
                           fill=look.bg, outline=look.border, width=max(1, int(k)))
    x = margin + 10 * k
    cy = margin + height / 2
    colour = look.error if state == "error" else look.accent
    if icon_font:
        draw.text((x + 6.5 * k, cy), _MIC, font=icon_font, fill=colour, anchor="mm")
    else:  # simple capsule mic
        draw.rounded_rectangle((x + 4 * k, cy - 6 * k, x + 9 * k, cy + 2 * k), radius=2.5 * k, fill=colour)
        draw.line((x + 6.5 * k, cy + 3 * k, x + 6.5 * k, cy + 6 * k), fill=colour, width=int(1.2 * k))
    x += 13 * k + 7 * k
    if state == "error":
        if text_font:
            draw.text((x, cy), message, font=text_font, fill=look.error, anchor="lm")
    else:
        for i in range(5):
            if state == "finishing":
                bar_h = 4 * k
                fill = look.muted
            else:
                level = levels[i] if i < len(levels) else 0.0
                bar_h = max(3.0, min(14.0, 3 + level / 0.05 * 11)) * k
                fill = colour
            bx = x + i * 5 * k
            draw.rounded_rectangle((bx, cy - bar_h / 2, bx + 3 * k, cy + bar_h / 2), radius=1.5 * k, fill=fill)
    return img.resize((max(1, int(w / ss)), max(1, int(h / ss))), Image.LANCZOS)


def _premultiplied_bgra(img: Image.Image) -> bytes:
    a = np.asarray(img, dtype=np.uint16)
    alpha = a[..., 3:4]
    rgb = (a[..., :3] * alpha + 127) // 255
    bgra = np.concatenate([rgb[..., ::-1], alpha], axis=2).astype(np.uint8)
    return bgra.tobytes()


class CaretIndicator:
    BAR_COUNT = 5
    GAP = 6
    ERROR_SECONDS = 4.0

    def __init__(self):
        self._hwnd = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock = threading.RLock()
        self._proc = _WNDPROC(self._wndproc)
        self._visible = False
        self._state = "listening"
        self._levels: list[float] = []
        self._message = ""
        self._look: Optional[Look] = None
        self._scale = 1.0
        self._pos = (0, 0)
        # Bumped by every show/hide: a delayed hide only acts if nothing has
        # happened since it was scheduled.
        self._generation = 0

    # -- window thread ---------------------------------------------------------------

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == _WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _loop(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName="ShuperWhisperIndicator")
        user32.RegisterClassW(ctypes.byref(wc))
        self._hwnd = user32.CreateWindowExW(_WS_EX, "ShuperWhisperIndicator", "ShuperWhisper Indicator",
                                            _WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
        self._ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def start(self) -> None:
        """Create the window (on its own thread). Safe to call more than once."""
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="indicator")
        self._thread.start()
        self._ready.wait(2.0)

    # -- drawing -----------------------------------------------------------------------

    def _paint(self) -> None:
        """Render the current state and push it to the layered window."""
        if not self._hwnd or not self._look:
            return
        img = render(self._look, self._scale, self._state, self._levels, self._message)
        w, h = img.size
        data = _premultiplied_bgra(img)
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        header = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=w, biHeight=-h,
                                   biPlanes=1, biBitCount=32, biCompression=0)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(mem, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(mem, bitmap)
        try:
            ctypes.memmove(bits, data, len(data))
            dst = wt.POINT(*self._pos)
            size = wt.SIZE(w, h)
            src = wt.POINT(0, 0)
            blend = _BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, per-pixel AC_SRC_ALPHA
            user32.UpdateLayeredWindow(self._hwnd, screen, ctypes.byref(dst), ctypes.byref(size), mem,
                                       ctypes.byref(src), 0, ctypes.byref(blend), _ULW_ALPHA)
        finally:
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)

    # -- placement -----------------------------------------------------------------------

    @staticmethod
    def _monitor_for(point):
        """(work area, DPI scale) of the monitor containing ``point``."""

        class _MI(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", wt.RECT),
                        ("rcWork", wt.RECT), ("dwFlags", ctypes.c_ulong)]

        hmon = ctypes.windll.user32.MonitorFromPoint(wt.POINT(*point), 2)  # NEAREST
        info = _MI(cbSize=ctypes.sizeof(_MI))
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        rc = info.rcWork
        scale = 1.0
        try:
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))
            scale = dx.value / 96.0
        except Exception:
            pass
        return (rc.left, rc.top, rc.right, rc.bottom), scale

    def _size(self) -> tuple[int, int]:
        return render(self._look or Look(True, "#4cc2ff"), self._scale, self._state, (), self._message).size

    def reposition(self, use_uia: bool = True) -> None:
        """Place the pill just under the caret (or at the bottom of the
        focused window if the caret can't be found)."""
        caret = caret_rect(use_uia=use_uia)
        if caret is None:
            window = foreground_rect()
            if window is None:
                return
            work, self._scale = self._monitor_for(((window[0] + window[2]) // 2, window[3]))
            w, h = self._size()
            self._pos = ((window[0] + window[2] - w) // 2, window[3] - h - int(24 * self._scale))
        else:
            work, self._scale = self._monitor_for((caret[0], caret[3]))
            w, h = self._size()
            self._pos = place_below(caret, work, (w, h), int(self.GAP * self._scale))
        with self._lock:
            if self._visible:
                self._paint()

    # -- public API ------------------------------------------------------------------------

    def show(self) -> None:
        with self._lock:
            self._generation += 1
            self._visible = True
            self._state, self._levels, self._message = "listening", [], ""
            self._look = Look.system()
        self.reposition(use_uia=True)
        with self._lock:
            if self._hwnd and self._visible:
                self._paint()
                user32.SetWindowPos(self._hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                                    _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = state
            if self._visible:
                self._paint()

    def show_error(self, message: str) -> None:
        with self._lock:
            self._generation += 1
            generation = self._generation
            was_visible = self._visible
            self._visible = True
            self._state, self._message = "error", message
            self._look = self._look or Look.system()
        if not was_visible:
            self.reposition(use_uia=False)
        with self._lock:
            if self._hwnd:
                self._paint()
                user32.SetWindowPos(self._hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                                    _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)

        def _later():
            time.sleep(self.ERROR_SECONDS)
            if self._generation == generation:  # nothing newer is showing
                self.hide()
        threading.Thread(target=_later, daemon=True).start()

    def hide(self) -> None:
        with self._lock:
            self._generation += 1
            self._visible = False
            if self._hwnd:
                user32.ShowWindow(self._hwnd, _SW_HIDE)

    def update_levels(self, levels) -> None:
        with self._lock:
            if not self._visible or self._state != "listening":
                return
            self._levels = list(levels[:self.BAR_COUNT])
            self._paint()

    @property
    def is_visible(self) -> bool:
        return self._visible

    def destroy(self) -> None:
        self.hide()
        if self._hwnd:
            user32.PostMessageW(self._hwnd, _WM_CLOSE, 0, 0)
