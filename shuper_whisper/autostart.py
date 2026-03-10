"""Windows autostart via HKCU registry — no admin required."""

import os
import sys
import winreg

_APP_NAME = "ShuperWhisper"
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _exe_path() -> str:
    """Return the path to the running executable."""
    if getattr(sys, "frozen", False):
        return sys.executable
    # Dev mode: use pythonw.exe + main.py
    return f'"{sys.executable}" "{os.path.abspath("main.py")}"'


def is_enabled() -> bool:
    """Check if autostart is currently enabled."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> None:
    """Enable autostart by writing to HKCU Run."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _exe_path())


def disable() -> None:
    """Disable autostart by removing the HKCU Run entry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        pass


def toggle() -> bool:
    """Toggle autostart. Returns the new state."""
    if is_enabled():
        disable()
        return False
    else:
        enable()
        return True
