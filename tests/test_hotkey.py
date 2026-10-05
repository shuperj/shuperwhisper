"""Tests for hotkey module with toggle mode."""

import pytest

from shuper_whisper import hotkey as hotkey_mod
from shuper_whisper.hotkey import HotkeyError, HotkeyManager, parse_hotkey


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


class FakeUser32:
    def __init__(self, ok=True):
        self.ok = ok

    def RegisterHotKey(self, *a):
        return 1 if self.ok else 0

    def UnregisterHotKey(self, *a):
        return 1

    def PeekMessageW(self, *a):
        return 0


class TestToggle:
    def test_first_press_starts_second_stops(self):
        calls = []
        hm = HotkeyManager("f9", lambda: calls.append("start"), lambda: calls.append("stop"))
        hm._on_trigger_press()
        assert hm.active
        hm._on_trigger_press()
        assert calls == ["start", "stop"] and not hm.active

    def test_reset_makes_next_press_start(self):
        calls = []
        hm = HotkeyManager("f9", lambda: calls.append("start"), lambda: calls.append("stop"))
        hm._on_trigger_press()
        hm.reset()
        hm._on_trigger_press()
        assert calls == ["start", "start"]


class TestRegister:
    def test_unknown_key_raises(self):
        hm = HotkeyManager("ctrl+notakey", lambda: None, lambda: None)
        with pytest.raises(HotkeyError, match="notakey"):
            hm.register()

    def test_register_failure_raises(self, monkeypatch):
        monkeypatch.setattr(hotkey_mod, "user32", FakeUser32(ok=False))
        hm = HotkeyManager("f9", lambda: None, lambda: None)
        with pytest.raises(HotkeyError, match="f9"):
            hm.register()
        assert not hm.registered

    def test_register_success(self, monkeypatch):
        monkeypatch.setattr(hotkey_mod, "user32", FakeUser32(ok=True))
        hm = HotkeyManager("f9", lambda: None, lambda: None)
        hm.register()
        assert hm.registered
        hm.unregister()
        assert not hm.registered
