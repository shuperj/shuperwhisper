"""Configuration management for ShuperWhisper."""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass


def _is_frozen() -> bool:
    """Return True if running as a PyInstaller frozen executable."""
    return getattr(sys, "frozen", False)


def _appdata_dir() -> str:
    """Return the ShuperWhisper directory under %APPDATA%."""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "ShuperWhisper")


def _project_root() -> str:
    """Return the project root directory (parent of shuper_whisper/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_config_path() -> str:
    """Return the path to config.json."""
    if _is_frozen():
        return os.path.join(_appdata_dir(), "config.json")
    return os.path.join(_project_root(), "config.json")


def _default_dictionary_path() -> str:
    """Return the path to dictionary.json."""
    if _is_frozen():
        return os.path.join(_appdata_dir(), "dictionary.json")
    return os.path.join(_project_root(), "dictionary.json")


SUPPORTED_LANGUAGES = {
    "auto": "Auto-detect",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "uk": "Ukrainian",
    "cs": "Czech",
    "ro": "Romanian",
    "hu": "Hungarian",
}

VALID_HOTKEY_MODES = ("hold", "toggle")
VALID_FORMAT_MODES = ("normal", "professional_email", "ai_prompt")
VALID_OVERLAY_POSITIONS = ("top_center", "center", "bottom_center")

FORMAT_MODE_LABELS = {
    "normal": "Normal",
    "professional_email": "Professional Email",
    "ai_prompt": "AI Prompt",
}

FORMAT_MODE_ORDER = list(VALID_FORMAT_MODES)


@dataclass
class AppConfig:
    hotkey: str = "ctrl+shift+space"
    model_size: str = "base"
    input_device: object = None  # int index or str name or None for default
    language: str = "en"
    autostart: bool = False
    smart_spacing: bool = True
    bullet_mode: bool = False
    email_mode: bool = False
    # Hotkey & format mode
    hotkey_mode: str = "hold"
    format_mode: str = "normal"
    # Tone settings (per format mode)
    email_tone: int = 3         # 1=warm/friendly, 3=standard professional, 5=very formal
    prompt_detail: int = 3      # 1=ultra-concise, 3=balanced, 5=comprehensive
    # Overlay
    overlay_position: str = "top_center"
    # Appearance
    accent_color: str = "#ff4466"
    bg_color: str = "#1a1a2e"

    VALID_MODELS = ("tiny", "base", "small", "medium", "large-v3")

    def validate(self) -> None:
        if self.model_size not in self.VALID_MODELS:
            self.model_size = "base"
        if not self.hotkey:
            self.hotkey = "ctrl+shift+space"
        if self.hotkey_mode not in VALID_HOTKEY_MODES:
            self.hotkey_mode = "hold"
        if self.format_mode not in VALID_FORMAT_MODES:
            self.format_mode = "normal"
        if self.overlay_position not in VALID_OVERLAY_POSITIONS:
            self.overlay_position = "top_center"
        self.email_tone = max(1, min(5, self.email_tone))
        self.prompt_detail = max(1, min(5, self.prompt_detail))
        if not re.match(r'^#[0-9a-fA-F]{6}$', self.accent_color):
            self.accent_color = "#ff4466"
        if not re.match(r'^#[0-9a-fA-F]{6}$', self.bg_color):
            self.bg_color = "#1a1a2e"

    def to_dict(self) -> dict:
        return asdict(self)


_CONFIG_FIELDS = [
    "hotkey", "model_size", "input_device", "language", "autostart",
    "smart_spacing", "bullet_mode", "email_mode",
    "hotkey_mode", "format_mode", "email_tone", "prompt_detail",
    "overlay_position",
    "accent_color", "bg_color",
]


def load_config(path: str | None = None) -> AppConfig:
    """Load configuration from a JSON file, falling back to defaults."""
    path = path or _default_config_path()
    config = AppConfig()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        for key in _CONFIG_FIELDS:
            if key in data:
                setattr(config, key, data[key])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    config.validate()
    return config


def save_config(config: AppConfig, path: str | None = None) -> None:
    """Save configuration to a JSON file."""
    path = path or _default_config_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(config.to_dict(), f, indent=4)
        print(f"Config saved to: {path}")
    except Exception as e:
        print(f"Error saving config: {e}")
