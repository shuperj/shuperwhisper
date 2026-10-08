"""Configuration management for ShuperWhisper."""

import json
import os
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


def config_dir() -> str:
    """Return the directory config.json lives in."""
    if _is_frozen():
        return _appdata_dir()
    return _project_root()


def _default_config_path() -> str:
    """Return the path to config.json."""
    return os.path.join(config_dir(), "config.json")


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

# "auto" uses an NVIDIA GPU when its CUDA runtime loads; "cpu" never tries.
VALID_COMPUTE = ("auto", "cpu")
# "auto": type live as you speak on a GPU, all at once when you stop on CPU.
VALID_LIVE_TYPING = ("auto", "on", "off")


def _validate_device(value: object) -> object:
    """Normalise the stored input device.

    Returns a ``{"name", "hostapi"}`` reference, a legacy int index (migrated to
    a reference at startup by audio_devices.migrate), or None for the default.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return {"name": value, "hostapi": None} if value.strip() else None
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name:
            hostapi = value.get("hostapi")
            return {"name": name, "hostapi": hostapi if isinstance(hostapi, str) else None}
    return None


@dataclass
class AppConfig:
    hotkey: str = "ctrl+shift+space"
    # "auto" picks base.en for English and base otherwise (transcriber.py).
    model_size: str = "auto"
    # {"name": str, "hostapi": str | None}, a legacy int index, or None for default.
    input_device: object = None
    language: str = "en"
    compute: str = "auto"
    live_typing: str = "auto"

    # The sizes worth offering, by benchmarks/results/*-full.md: medium and
    # large-v3 are bigger than large-v3-turbo without being better for this.
    VALID_MODELS = ("auto", "large-v3-turbo", "small", "base", "tiny")

    def validate(self) -> None:
        if self.model_size not in self.VALID_MODELS:
            self.model_size = "auto"
        if not self.hotkey:
            self.hotkey = "ctrl+shift+space"
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = "en"
        if self.compute not in VALID_COMPUTE:
            self.compute = "auto"
        if self.live_typing not in VALID_LIVE_TYPING:
            self.live_typing = "auto"
        self.input_device = _validate_device(self.input_device)

    def to_dict(self) -> dict:
        return asdict(self)


_CONFIG_FIELDS = ["hotkey", "model_size", "input_device", "language", "compute", "live_typing"]


def load_config(path: str | None = None) -> AppConfig:
    """Load configuration from a JSON file, falling back to defaults.

    Keys from older versions (format modes, colours, ...) are ignored.
    """
    path = path or _default_config_path()
    config = AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in _CONFIG_FIELDS:
            if key in data:
                setattr(config, key, data[key])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    config.validate()
    return config


def save_config(config: AppConfig, path: str | None = None) -> None:
    """Save configuration to a JSON file. Raises OSError on failure."""
    path = path or _default_config_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=4)
