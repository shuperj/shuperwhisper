#!/usr/bin/env python3
"""
ShuperWhisper - Hotkey-based voice dictation for Windows.

Usage:
    python main.py                  Start dictation (system tray)
    python main.py --console        Start dictation (console mode)
    python main.py --list-devices   Show audio input devices

This is a thin wrapper. The real entry point is shuper_whisper.app:main, which
is what pyproject's [project.gui-scripts] and the PyInstaller build run.
Keeping the logic there means the dev path and the packaged path cannot drift
apart -- see issue #11, where DPI awareness lived only here and so was
silently absent from every installed copy.
"""

from shuper_whisper.app import main

if __name__ == "__main__":
    main()
