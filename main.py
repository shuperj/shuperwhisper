#!/usr/bin/env python3
"""
ShuperWhisper - Hotkey-based voice dictation for Windows.

Usage:
    python main.py                  Start dictation (system tray)
    python main.py --console        Start dictation (console mode)
    python main.py --list-devices   Show audio input devices
"""

import multiprocessing
import os
import sys

from shuper_whisper.config import load_config


def _load_env() -> None:
    """Load environment variables from D:/dev/.env if available."""
    env_path = os.path.join("D:", os.sep, "dev", ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
    except OSError:
        pass


def main():
    multiprocessing.freeze_support()

    # Load API keys (ANTHROPIC_API_KEY, etc.) from workspace .env
    _load_env()

    if "--list-devices" in sys.argv:
        from shuper_whisper.app import list_devices

        list_devices()
        sys.exit(0)

    config = load_config()

    if "--console" in sys.argv:
        from shuper_whisper.app import ShuperWhisperApp

        app = ShuperWhisperApp(config)
        app.run()
    else:
        from shuper_whisper.tray import TrayController

        tray = TrayController(config)
        tray.run()


if __name__ == "__main__":
    main()
