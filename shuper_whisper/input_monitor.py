"""Notice the user's own keyboard/mouse input while dictation is typing.

Low-level hooks are installed only for the length of a dictation session.
Events we injected ourselves (SendInput) carry the INJECTED flag and are
ignored, as are the hotkey's own keys.
"""

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Iterable, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
_CLICKS = (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wt.HINSTANCE, wt.DWORD)
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
user32.GetMessageW.argtypes = (ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
user32.PostThreadMessageW.argtypes = (wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)
kernel32.GetModuleHandleW.restype = wt.HMODULE


class InputMonitor:
    def __init__(self, ignore_vks: Iterable[int] = ()):
        self._ignore = frozenset(ignore_vks)
        self._user_input = False
        self._thread: Optional[threading.Thread] = None
        self._thread_id = 0
        self._ready = threading.Event()
        # Keep the ctypes callbacks alive for as long as the hooks are installed.
        self._kb_proc = _HOOKPROC(self._keyboard_hook)
        self._mouse_proc = _HOOKPROC(self._mouse_hook)

    # Pure handlers (unit-tested) ------------------------------------------------

    def _on_key(self, vk: int, flags: int) -> None:
        if not flags & LLKHF_INJECTED and vk not in self._ignore:
            self._user_input = True

    def _on_mouse(self, message: int, flags: int) -> None:
        if message in _CLICKS and not flags & LLMHF_INJECTED:
            self._user_input = True

    # Hook plumbing ----------------------------------------------------------------

    def _keyboard_hook(self, code, wparam, lparam):
        if code >= 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            self._on_key(info.vkCode, info.flags)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _mouse_hook(self, code, wparam, lparam):
        if code >= 0 and wparam in _CLICKS:
            info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            self._on_mouse(wparam, info.flags)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        module = kernel32.GetModuleHandleW(None)
        kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, module, 0)
        mouse = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, module, 0)
        self._ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        for hook in (kb, mouse):
            if hook:
                user32.UnhookWindowsHookEx(hook)

    def start(self) -> None:
        if self._thread:
            return
        self._user_input = False
        self._ready.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="input-monitor")
        self._thread.start()
        self._ready.wait(1.0)

    def stop(self) -> None:
        if not self._thread:
            return
        user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(1.0)
        self._thread = None

    def clear(self) -> None:
        self._user_input = False

    @property
    def user_input(self) -> bool:
        return self._user_input
