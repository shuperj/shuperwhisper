"""Windows theme: light/dark, the user's accent colour, title-bar colour."""

import ctypes
import winreg

DEFAULT_ACCENTS = {"light": "#0067c0", "dark": "#4cc2ff"}
_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_ACCENT = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
DWMWA_USE_IMMERSIVE_DARK_MODE = 20


def _read(path: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def apps_use_dark() -> bool:
    return _read(_PERSONALIZE, "AppsUseLightTheme") == 0


def parse_accent_palette(raw) -> dict[str, str]:
    """AccentPalette is 8 RGBA swatches, lightest first: Light3, Light2,
    Light1, Base, Dark1, Dark2, Dark3, (unused). Windows uses Dark1 for
    accent fills in light mode and Light2 in dark mode."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 32:
        return dict(DEFAULT_ACCENTS)

    def swatch(i: int) -> str:
        r, g, b = raw[i * 4:i * 4 + 3]
        return f"#{r:02x}{g:02x}{b:02x}"
    return {"light": swatch(4), "dark": swatch(1)}


def accent_colors() -> dict[str, str]:
    return parse_accent_palette(_read(_ACCENT, "AccentPalette"))


def apply_window_theme(hwnd: int, dark: bool) -> None:
    """Dark or light title bar to match the page."""
    value = ctypes.c_int(1 if dark else 0)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except OSError:
        pass
