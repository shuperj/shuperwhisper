"""Where is the text caret, and which field has focus?"""

import ctypes
import ctypes.wintypes as wt

from . import uia

user32 = ctypes.windll.user32


def field_id() -> tuple:
    """(focused HWND, UIA RuntimeId). Browsers share one HWND across all their
    fields, so the UIA id is what tells two fields on a page apart."""
    foreground, info = uia.gui_thread_info()
    hwnd = (info.hwndFocus if info and info.hwndFocus else foreground) or 0
    return (int(hwnd), uia.focused_element_id())


def caret_rect(use_uia: bool = False):
    """Screen rect of the caret, from Win32 (classic controls) or UIA."""
    _foreground, info = uia.gui_thread_info()
    if info and info.hwndCaret:
        rc = info.rcCaret
        top_left = wt.POINT(rc.left, rc.top)
        bottom_right = wt.POINT(rc.right, rc.bottom)
        for point in (top_left, bottom_right):
            user32.ClientToScreen(info.hwndCaret, ctypes.byref(point))
            # A DPI-unaware app reports logical pixels; we work in physical.
            # (No-op for DPI-aware windows.)
            _to_physical(info.hwndCaret, point)
        return (top_left.x, top_left.y, max(bottom_right.x, top_left.x + 1), bottom_right.y)
    return uia.caret_bounds() if use_uia else None


def _to_physical(hwnd, point) -> None:
    try:
        user32.LogicalToPhysicalPointForPerMonitorDPI(hwnd, ctypes.byref(point))
    except AttributeError:  # before Windows 8.1
        pass


def foreground_rect():
    foreground = user32.GetForegroundWindow()
    rect = wt.RECT()
    if foreground and user32.GetWindowRect(foreground, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def place_below(caret, work_area, size, gap):
    """Top-left for a box of ``size`` just under ``caret``, kept on screen."""
    left, top, _right, bottom = caret
    wa_left, wa_top, wa_right, wa_bottom = work_area
    width, height = size
    x = min(max(left - gap, wa_left), wa_right - width)
    y = bottom + gap
    if y + height > wa_bottom:
        y = top - height - gap
    return x, max(y, wa_top)
