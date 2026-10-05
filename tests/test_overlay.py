"""CaretIndicator non-GUI behaviour."""

from shuper_whisper import overlay as ov
from shuper_whisper.overlay import CaretIndicator


class Win:
    def __init__(self):
        self.js = []

    def evaluate_js(self, js):
        self.js.append(js)


def test_initially_hidden():
    assert CaretIndicator().is_visible is False


def test_show_hide_and_states_call_js():
    ind = CaretIndicator()
    w = Win()
    ind.set_window(w)
    ind.show()
    ind.set_state("finishing")
    ind.hide()
    assert w.js[0].startswith("show(") and "setState('finishing')" in w.js and w.js[-1] == "hide()"


def test_error_message_is_escaped():
    ind = CaretIndicator()
    ind.ERROR_SECONDS = 0
    w = Win()
    ind.set_window(w)
    ind.show_error("Can't type into 'admin' windows")
    assert 'showError("Can\'t type into \'admin\' windows")' in w.js


def test_levels_only_while_visible():
    ind = CaretIndicator()
    w = Win()
    ind.set_window(w)
    ind.update_levels([0.1] * 5)
    assert w.js == []


def test_reposition_uses_caret_then_window(monkeypatch):
    moves = []
    ind = CaretIndicator()
    ind._hwnd = 1
    monkeypatch.setattr(ind, "_move", lambda x, y, w, h: moves.append((x, y)))
    monkeypatch.setattr(ind, "_monitor_for", lambda pt: ((0, 0, 1920, 1040), 1.0))
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: (500, 300, 502, 320))
    ind.reposition()
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: None)
    monkeypatch.setattr(ov, "foreground_rect", lambda: (100, 100, 900, 700))
    ind.reposition()
    assert moves[0] == (494, 326)
    assert moves[1][1] == 700 - ind.HEIGHT - 24


def test_error_auto_hide_spares_a_newer_session(monkeypatch):
    import time
    ind = CaretIndicator()
    ind.ERROR_SECONDS = 0.05
    w = Win()
    ind.set_window(w)
    ind.show_error("Microphone: unplugged")
    ind.show()                       # the user retries straight away
    time.sleep(0.2)
    assert ind.is_visible and w.js[-1] == "show()"
