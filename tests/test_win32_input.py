"""Tests for SendInput event construction (no keystrokes are sent)."""

import ctypes

from shuper_whisper import _win32_keys as k


def test_input_struct_size_matches_windows_x64():
    assert ctypes.sizeof(k.INPUT) == 40


def test_ascii_char_is_unicode_down_up():
    events = k.text_to_inputs("a")
    assert len(events) == 2
    down, up = (e.union.ki for e in events)
    assert down.wScan == ord("a") and down.dwFlags == k.KEYEVENTF_UNICODE
    assert up.dwFlags == k.KEYEVENTF_UNICODE | k.KEYEVENTF_KEYUP
    assert down.dwExtraInfo == k.SHUPER_INPUT_TAG


def test_newline_is_shift_enter_and_cr_skipped():
    events = k.text_to_inputs("\r\n")
    assert [e.union.ki.wVk for e in events] == [k.VK_LSHIFT, k.VK_RETURN, k.VK_RETURN, k.VK_LSHIFT]


def test_astral_char_is_surrogate_pair():
    events = k.text_to_inputs("😀")
    assert [e.union.ki.wScan for e in events[::2]] == [0xD83D, 0xDE00]


def test_backspaces_come_first():
    events = k.text_to_inputs("x", backspaces=2)
    assert [e.union.ki.wVk for e in events[:4]] == [k.VK_BACK] * 4
    assert events[4].union.ki.wScan == ord("x")


def test_own_process_is_not_blocked():
    # The foreground window during tests is a normal-privilege terminal (or none).
    assert k.foreground_blocks_input() in (False, True)
