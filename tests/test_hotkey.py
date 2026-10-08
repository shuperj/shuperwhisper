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


class Keyboard:
    """A fake trigger key and clock for driving the gestures."""

    def __init__(self, mode="tap"):
        self.t = 0.0
        self.down = False
        self.calls = []
        self.hm = HotkeyManager("f9", lambda: self.calls.append("start"), lambda: self.calls.append("stop"),
                                on_cancel=lambda: self.calls.append("cancel"), mode=mode,
                                key_down=lambda vk: self.down, clock=lambda: self.t)

    def press(self):
        self.down = True
        self.hm._on_trigger_press()

    def release_after(self, seconds):
        self.t += seconds
        self.down = False
        self.hm._poll()

    def wait(self, seconds):
        self.t += seconds
        self.hm._poll()


class TestTapMode:
    def test_tap_starts_and_the_next_tap_stops(self):
        k = Keyboard("tap")
        k.press()
        k.release_after(0.15)
        k.wait(5.0)
        assert k.calls == ["start"] and k.hm.active
        k.press()
        k.release_after(0.1)
        assert k.calls == ["start", "stop"] and not k.hm.active

    def test_hold_is_push_to_talk(self):
        k = Keyboard("tap")
        k.press()
        assert k.calls == ["start"]        # starts on key-down: no words lost
        k.wait(1.0)                        # still held: keeps going
        k.release_after(1.0)
        assert k.calls == ["start", "stop"] and not k.hm.active

    def test_reset_makes_next_press_start(self):
        k = Keyboard("tap")
        k.press()
        k.release_after(0.1)
        k.hm.reset()                       # e.g. auto-stop after silence
        k.press()
        assert k.calls == ["start", "start"]


class TestDoubleTapMode:
    def test_double_tap_locks_on_and_a_tap_stops(self):
        k = Keyboard("double")
        k.press()
        k.release_after(0.1)
        k.wait(0.15)
        k.press()                          # second tap in time
        k.release_after(0.1)
        k.wait(5.0)
        assert k.calls == ["start"] and k.hm.active
        k.press()
        assert k.calls == ["start", "stop"]

    def test_a_lone_tap_cancels(self):
        k = Keyboard("double")
        k.press()
        k.release_after(0.1)
        k.wait(0.5)
        assert k.calls == ["start", "cancel"] and not k.hm.active

    def test_hold_is_push_to_talk(self):
        k = Keyboard("double")
        k.press()
        k.release_after(0.8)
        assert k.calls == ["start", "stop"]


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
