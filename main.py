#!/usr/bin/env python3
"""
ShuperWhisper - Hotkey-based voice dictation for Windows.

Usage:
    python main.py                  Start dictation
    python main.py --list-devices   Show audio input devices
"""

import sys

from shuper_whisper.app import ShuperWhisperApp, list_devices
from shuper_whisper.config import load_config


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list-devices":
        list_devices()
        sys.exit(0)

    config = load_config()
    app = ShuperWhisperApp(config)
    app.run()


if __name__ == "__main__":
    main()
