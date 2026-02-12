"""Configuration management for ShuperWhisper."""

import json
import os
from dataclasses import asdict, dataclass, field


def _default_config_path() -> str:
    """Return the path to config.json next to the application."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
    )


def _appdata_dir() -> str:
    """Return the ShuperWhisper directory under %APPDATA%."""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "ShuperWhisper")


@dataclass
class AppConfig:
    hotkey: str = "ctrl+shift+space"
    model_size: str = "base"
    input_device: object = None  # int index or str name or None for default
    language: str = "en"

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
