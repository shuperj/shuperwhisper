"""Win32 keyboard utilities using ctypes — no admin, no hooks."""

import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32

# Win32 constants
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
KEYEVENTF_KEYUP = 0x0002

# Modifier name -> MOD_* flag (for RegisterHotKey)
MODIFIER_FLAG_MAP = {
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "windows": MOD_WIN,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "left ctrl": MOD_CONTROL,
    "right ctrl": MOD_CONTROL,
    "left shift": MOD_SHIFT,
    "right shift": MOD_SHIFT,
    "left alt": MOD_ALT,
    "right alt": MOD_ALT,
    "left windows": MOD_WIN,
    "right windows": MOD_WIN,
}

# Modifier name -> list of VK codes (for GetAsyncKeyState polling)
MODIFIER_VK_MAP = {
    "ctrl": [0xA2, 0xA3],       # VK_LCONTROL, VK_RCONTROL
    "shift": [0xA0, 0xA1],      # VK_LSHIFT, VK_RSHIFT
    "alt": [0xA4, 0xA5],        # VK_LMENU, VK_RMENU
    "windows": [0x5B, 0x5C],    # VK_LWIN, VK_RWIN
    "win": [0x5B, 0x5C],
    "super": [0x5B, 0x5C],
    "left ctrl": [0xA2],
    "right ctrl": [0xA3],
    "left shift": [0xA0],
    "right shift": [0xA1],
    "left alt": [0xA4],
    "right alt": [0xA5],
    "left windows": [0x5B],
    "right windows": [0x5C],
}

# Key name -> VK code
VK_MAP = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "page up": 0x21,
    "pagedown": 0x22,
    "page down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "capslock": 0x14,
    "caps lock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "printscreen": 0x2C,
    "print screen": 0x2C,
    "pause": 0x13,
    # F-keys F1-F24
    **{f"f{i}": 0x70 + (i - 1) for i in range(1, 25)},
    # Letters a-z (VK codes are uppercase ASCII)
    **{chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)},
    # Digits 0-9
    **{str(i): 0x30 + i for i in range(10)},
    # Numpad
    **{f"num {i}": 0x60 + i for i in range(10)},
    "num +": 0x6B,
    "num -": 0x6D,
    "num *": 0x6A,
    "num /": 0x6F,
    "num .": 0x6E,
    # Punctuation (common ones)
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}

# Reverse map: VK code -> key name (for hotkey capture)
VK_TO_NAME = {}
for _name, _vk in VK_MAP.items():
    if _vk not in VK_TO_NAME:
        VK_TO_NAME[_vk] = _name

# Modifier VK codes (for distinguishing modifiers from trigger keys)
_ALL_MODIFIER_VKS = {0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C,
                     0x10, 0x11, 0x12}  # VK_SHIFT, VK_CONTROL, VK_MENU generic


def get_vk(key_name: str) -> int:
    """Get the VK code for a key name. Returns 0 if not found."""
    return VK_MAP.get(key_name.lower().strip(), 0)


def get_mod_flags(modifier_names: list[str]) -> int:
    """Combine modifier names into a MOD_* bitmask with MOD_NOREPEAT."""
    flags = MOD_NOREPEAT
    for mod in modifier_names:
        flags |= MODIFIER_FLAG_MAP.get(mod.lower().strip(), 0)
    return flags


def is_key_down(vk_code: int) -> bool:
    """Check if a key is currently pressed via GetAsyncKeyState."""
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)


def is_modifier_down(modifier_name: str) -> bool:
    """Check if any VK for a named modifier is currently pressed."""
    vks = MODIFIER_VK_MAP.get(modifier_name.lower().strip(), [])
    return any(is_key_down(vk) for vk in vks)


def send_combo(*vk_codes: int) -> None:
    """Simulate a key combination (press all, release in reverse)."""
    for vk in vk_codes:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vk_codes):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


# Common VK constants for direct use
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt
VK_HOME = 0x24
VK_RIGHT = 0x27
VK_C = 0x43
VK_V = 0x56
