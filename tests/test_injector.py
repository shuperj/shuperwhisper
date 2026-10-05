"""Tests for TextInjector with fake Win32/UIA providers."""

from shuper_whisper.injector import TextInjector


def make(context=None, hwnd=1):
    sent = []
    state = {"context": context, "hwnd": hwnd}
    inj = TextInjector(
        send=lambda text, backspaces=0: sent.append(text),
        read_context=lambda: state["context"],
        foreground=lambda: state["hwnd"],
        wait_modifiers=lambda: True,
    )
    return inj, sent, state


def test_uses_uia_context():
    inj, sent, _ = make(context="Done.")
    assert inj.inject("next thing.") == " Next thing."
    assert sent == [" Next thing."]


def test_unknown_context_capitalises_without_space():
    inj, sent, _ = make(context=None)
    inj.inject("hello.")
    assert sent == ["Hello."]


def test_falls_back_to_own_history_in_same_window():
    inj, sent, _ = make(context=None)
    inj.inject("first part")
    inj.inject("And more.")
    assert sent == ["First part", " and more."]


def test_history_ignored_in_other_window():
    inj, sent, state = make(context=None)
    inj.inject("first part")
    state["hwnd"] = 2
    inj.inject("then more.")
    assert sent[-1] == "Then more."


def test_empty_text_sends_nothing():
    inj, sent, _ = make()
    assert inj.inject("") == ""
    assert sent == []
