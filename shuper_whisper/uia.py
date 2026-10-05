"""What precedes the caret in the focused control, via UI Automation.

Best effort: many controls don't expose TextPattern and some apps hang on UIA
calls, so everything runs on one worker thread with a short timeout and
returns None when the answer is unknown.
"""

import ctypes
import ctypes.wintypes as wt
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

_CONTEXT_CHARS = 200
_UIA_TEXT_PATTERN_ID = 10014
_EM_GETSEL = 0x00B0
_WM_GETTEXT = 0x000D
_WM_GETTEXTLENGTH = 0x000E
_SMTO_ABORTIFHUNG = 0x0002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendMessageTimeoutW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                        ctypes.POINTER(ctypes.c_size_t))
_user32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.c_void_p)
_user32.GetForegroundWindow.restype = wt.HWND
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia")
_local = threading.local()


def _client():
    if getattr(_local, "uia", None) is None:
        import comtypes
        import comtypes.client
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass  # importing comtypes already initialised COM on this thread
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as mod
        _local.mod = mod
        _local.uia = comtypes.client.CreateObject(mod.CUIAutomation, interface=mod.IUIAutomation)
    return _local.uia, _local.mod


def _text_before_caret() -> str | None:
    uia, _mod = _client()
    element = uia.GetFocusedElement()
    return _text_before_caret_of(element) if element else None


def _text_before_caret_of(element) -> str | None:
    _uia, mod = _client()
    pattern = element.GetCurrentPattern(_UIA_TEXT_PATTERN_ID)
    if not pattern:
        return None
    text_pattern = pattern.QueryInterface(mod.IUIAutomationTextPattern)
    selection = text_pattern.GetSelection()
    if not selection or selection.Length == 0:
        return None
    caret = selection.GetElement(0).Clone()
    # Collapse to the selection start, then reach back a bounded distance.
    caret.MoveEndpointByRange(mod.TextPatternRangeEndpoint_End, caret,
                              mod.TextPatternRangeEndpoint_Start)
    caret.MoveEndpointByUnit(mod.TextPatternRangeEndpoint_Start, mod.TextUnit_Character,
                             -_CONTEXT_CHARS)
    return caret.GetText(-1)


def _focused_element_id() -> tuple | None:
    uia, _mod = _client()
    element = uia.GetFocusedElement()
    return tuple(element.GetRuntimeId()) if element else None


def _run(fn, timeout: float):
    try:
        return _executor.submit(fn).result(timeout=timeout)
    except FutureTimeout:
        return None
    except Exception:
        return None


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


def gui_thread_info() -> tuple[int, "_GUITHREADINFO | None"]:
    """(foreground HWND, GUITHREADINFO of its thread) -- focus and caret details."""
    foreground = _user32.GetForegroundWindow()
    if not foreground:
        return 0, None
    thread_id = _user32.GetWindowThreadProcessId(foreground, None)
    info = _GUITHREADINFO(cbSize=ctypes.sizeof(_GUITHREADINFO))
    if not _user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return foreground, None
    return foreground, info


def _send(hwnd, message, wparam, lparam) -> int | None:
    result = ctypes.c_size_t()
    ok = _user32.SendMessageTimeoutW(hwnd, message, wparam, lparam, _SMTO_ABORTIFHUNG,
                                     200, ctypes.byref(result))
    return result.value if ok else None


def _classic_edit_before_caret_of(hwnd) -> str | None:
    """Classic Win32 EDIT controls expose no UIA TextPattern; ask them directly."""
    name = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, name, 64)
    if name.value.lower() != "edit":
        return None
    selection = _send(hwnd, _EM_GETSEL, 0, 0)
    length = _send(hwnd, _WM_GETTEXTLENGTH, 0, 0)
    if selection is None or length is None:
        return None
    buffer = ctypes.create_unicode_buffer(length + 1)
    if _send(hwnd, _WM_GETTEXT, length + 1, ctypes.addressof(buffer)) is None:
        return None
    start = selection & 0xFFFF
    return buffer.value[:start][-_CONTEXT_CHARS:]


def text_before_caret(timeout: float = 0.3) -> str | None:
    """Up to 200 characters before the caret, "" for an empty field, None if unknown."""
    text = _run(_text_before_caret, timeout)
    if text is not None:
        return text
    _foreground, info = gui_thread_info()
    return _classic_edit_before_caret_of(info.hwndFocus) if info and info.hwndFocus else None


def _caret_bounds_of(element):
    _uia, mod = _client()
    pattern = element.GetCurrentPattern(_UIA_TEXT_PATTERN_ID)
    if not pattern:
        return None
    selection = pattern.QueryInterface(mod.IUIAutomationTextPattern).GetSelection()
    if not selection or selection.Length == 0:
        return None
    rng = selection.GetElement(0).Clone()
    # A collapsed range usually has no rectangle; measure the character before it.
    rng.MoveEndpointByRange(mod.TextPatternRangeEndpoint_End, rng, mod.TextPatternRangeEndpoint_Start)
    rng.MoveEndpointByUnit(mod.TextPatternRangeEndpoint_Start, mod.TextUnit_Character, -1)
    rects = list(rng.GetBoundingRectangles() or ())
    if len(rects) < 4:
        return None
    left, top, width, height = rects[-4:]
    right = int(left + width)
    return (right, int(top), right + 1, int(top + height))


def _caret_bounds():
    uia, _mod = _client()
    element = uia.GetFocusedElement()
    return _caret_bounds_of(element) if element else None


def caret_bounds(timeout: float = 0.15):
    """Screen rect just after the character before the caret, or None."""
    return _run(_caret_bounds, timeout)


def focused_element_id(timeout: float = 0.3) -> tuple | None:
    """UIA RuntimeId of the focused element: identifies "the same field"."""
    return _run(_focused_element_id, timeout)
