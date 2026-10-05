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


def test_hotkey_chord_ignored():
    held = {0xA2}
    m = InputMonitor(ignore_vks=(0xA2,), trigger_vk=0x20, key_down=lambda vk: vk in held)
    m._on_key(0xA2, 0)
    m._on_key(0x20, 0)
    assert not m.user_input


def test_plain_space_while_typing_counts():
    m = InputMonitor(ignore_vks=(0xA2,), trigger_vk=0x20, key_down=lambda vk: False)
    m._on_key(0x20, 0)
    assert m.user_input


def test_modifierless_hotkey_trigger_always_ignored():
    m = InputMonitor(trigger_vk=0x78, key_down=lambda vk: False)
    m._on_key(0x78, 0)
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
