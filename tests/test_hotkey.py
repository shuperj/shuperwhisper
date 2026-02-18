"""Tests for hotkey module with toggle mode."""

import pytest

from shuper_whisper.hotkey import HotkeyManager, parse_hotkey


class TestParseHotkey:
    def test_single_key(self):
        mods, trigger = parse_hotkey("f16")
        assert mods == []
        assert trigger == "f16"

    def test_ctrl_shift_space(self):
        mods, trigger = parse_hotkey("ctrl+shift+space")
        assert mods == ["ctrl", "shift"]
        assert trigger == "space"

    def test_windows_key_normalized(self):
        mods, trigger = parse_hotkey("win+space")
        assert mods == ["windows"]
        assert trigger == "space"

    def test_super_key_normalized(self):
        mods, trigger = parse_hotkey("super+a")
        assert mods == ["windows"]
        assert trigger == "a"

    def test_whitespace_stripped(self):
        mods, trigger = parse_hotkey("ctrl + shift + a")
        assert mods == ["ctrl", "shift"]
        assert trigger == "a"

    def test_case_insensitive(self):
        mods, trigger = parse_hotkey("Ctrl+Shift+A")
        assert mods == ["ctrl", "shift"]
        assert trigger == "a"


class TestHotkeyManagerInit:
    def test_smart_mode_default(self):
        hm = HotkeyManager("ctrl+space", lambda: None, lambda: None)
        assert hm.mode == "smart"

    def test_smart_mode_always(self):
        # Mode parameter is ignored, always uses smart mode
        hm = HotkeyManager("ctrl+space", lambda: None, lambda: None, mode="hold")
        assert hm.mode == "smart"

    def test_mode_property(self):
        hm = HotkeyManager("ctrl+space", lambda: None, lambda: None)
        assert hm.mode == "smart"


class TestSmartModeLogic:
    def test_starts_not_recording(self):
        hm = HotkeyManager("f5", lambda: None, lambda: None)
        assert hm._recording is False
        assert hm._toggle_active is False

    def test_not_registered_by_default(self):
        hm = HotkeyManager("f5", lambda: None, lambda: None)
        assert hm._registered is False

    def test_press_time_initially_none(self):
        hm = HotkeyManager("f5", lambda: None, lambda: None)
        assert hm._press_time is None


class TestArrowKeyRegistration:
    def test_arrow_hooks_initially_empty(self):
        hm = HotkeyManager("f5", lambda: None, lambda: None, mode="toggle")
        assert len(hm._arrow_hooks) == 0

    def test_unregister_arrow_keys_noop_when_empty(self):
        hm = HotkeyManager("f5", lambda: None, lambda: None, mode="toggle")
        hm.unregister_arrow_keys()  # Should not raise
        assert len(hm._arrow_hooks) == 0
