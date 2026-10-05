from shuper_whisper.input_monitor import (
    LLKHF_INJECTED, LLMHF_INJECTED, WM_LBUTTONDOWN, WM_MOUSEMOVE, InputMonitor,
)


def test_physical_key_flags_input():
    m = InputMonitor()
    m._on_key(0x41, 0)
    assert m.user_input


def test_injected_key_ignored():
    m = InputMonitor()
    m._on_key(0x41, LLKHF_INJECTED)
    assert not m.user_input


def test_hotkey_keys_ignored():
    m = InputMonitor(ignore_vks=(0xA2, 0x20))
    m._on_key(0x20, 0)
    m._on_key(0xA2, 0)
    assert not m.user_input


def test_click_flags_input_but_move_does_not():
    m = InputMonitor()
    m._on_mouse(WM_MOUSEMOVE, 0)
    assert not m.user_input
    m._on_mouse(WM_LBUTTONDOWN, 0)
    assert m.user_input


def test_injected_click_ignored_and_clear_resets():
    m = InputMonitor()
    m._on_mouse(WM_LBUTTONDOWN, LLMHF_INJECTED)
    assert not m.user_input
    m._on_key(0x41, 0)
    m.clear()
    assert not m.user_input
