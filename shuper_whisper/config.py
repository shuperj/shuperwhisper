"""Configuration management for ShuperWhisper."""

import json
import os
import sys
from dataclasses import asdict, dataclass, field


def _is_frozen() -> bool:
    """Return True if running as a PyInstaller frozen executable."""
    return getattr(sys, "frozen", False)


def _appdata_dir() -> str:
    """Return the ShuperWhisper directory under %APPDATA%."""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "ShuperWhisper")


def _default_config_path() -> str:
    """Return the path to config.json.

    When frozen (PyInstaller exe), use %APPDATA%/ShuperWhisper/config.json.
    Otherwise, use config.json next to the source tree.
    """
    if _is_frozen():
        return os.path.join(_appdata_dir(), "config.json")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
    )


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

    VALID_MODELS = ("tiny", "base", "small", "medium", "large-v3")

    def validate(self) -> None:
        if self.model_size not in self.VALID_MODELS:
            self.model_size = "base"
        if not self.hotkey:
            self.hotkey = "ctrl+shift+space"

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: str | None = None) -> AppConfig:
    """Load configuration from a JSON file, falling back to defaults."""
    path = path or _default_config_path()
    config = AppConfig()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        config.hotkey = data.get("hotkey", config.hotkey)
        config.model_size = data.get("model_size", config.model_size)
        config.input_device = data.get("input_device", config.input_device)
        config.language = data.get("language", config.language)
        config.autostart = data.get("autostart", config.autostart)
        config.smart_spacing = data.get("smart_spacing", config.smart_spacing)
        config.bullet_mode = data.get("bullet_mode", config.bullet_mode)
        config.email_mode = data.get("email_mode", config.email_mode)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    config.validate()
    return config


def save_config(config: AppConfig, path: str | None = None) -> None:
    """Save configuration to a JSON file."""
    path = path or _default_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=4)
