#!/usr/bin/env python3
"""
ShuperWhisper - Hotkey-based voice dictation for Windows.

Usage:
    python main.py                  Start dictation (system tray)
    python main.py --console        Start dictation (console mode)
    python main.py --list-devices   Show audio input devices
"""

import multiprocessing
import sys

from shuper_whisper.config import load_config


def main():
    multiprocessing.freeze_support()

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
