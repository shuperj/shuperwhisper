"""CaretIndicator: rendering and behaviour that doesn't need a real window."""

import time

from shuper_whisper import overlay as ov
from shuper_whisper.overlay import CaretIndicator, Look, render

DARK = Look(True, "#4cc2ff")


def test_render_is_transparent_around_the_pill():
    img = render(DARK, 1.0, "listening", [0.03] * 5)
    w, h = img.size
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((w - 1, h - 1))[3] == 0
    assert img.getpixel((w // 2, h // 2))[3] > 200


def test_render_scales_and_widens_for_errors():
    small = render(DARK, 1.0)
    big = render(DARK, 2.0)
    assert abs(big.size[0] - 2 * small.size[0]) <= 2
    assert render(DARK, 1.0, "error", message="Can't type into admin windows").size[0] > small.size[0]


def test_premultiplied_pixels():
    from PIL import Image
    img = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
    assert ov._premultiplied_bgra(img) == bytes([25, 50, 100, 128])


def _indicator(monkeypatch):
    ind = CaretIndicator()
    monkeypatch.setattr(ind, "_monitor_for", lambda pt: ((0, 0, 1920, 1040), 1.0))
    monkeypatch.setattr(ov.Look, "system", classmethod(lambda cls: DARK))
    return ind


def test_reposition_under_caret_then_window_bottom(monkeypatch):
    ind = _indicator(monkeypatch)
    ind._look = DARK
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: (500, 300, 502, 320))
    ind.reposition()
    assert ind._pos == (494, 326)
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: None)
    monkeypatch.setattr(ov, "foreground_rect", lambda: (100, 100, 900, 700))
    ind.reposition()
    w, h = ind._size()
    assert ind._pos == ((1000 - w) // 2, 700 - h - 24)


def test_error_auto_hide_spares_a_newer_session(monkeypatch):
    ind = _indicator(monkeypatch)
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: (500, 300, 502, 320))
    ind.ERROR_SECONDS = 0.05
    ind.show_error("Microphone: unplugged")
    ind.show()                       # the user retries straight away
    time.sleep(0.2)
    assert ind.is_visible and ind._state == "listening"


def test_levels_ignored_when_hidden_or_not_listening(monkeypatch):
    ind = _indicator(monkeypatch)
    ind.update_levels([0.1] * 5)
    assert ind._levels == []
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: (500, 300, 502, 320))
    ind.show()
    ind.update_levels([0.1] * 7)
    assert ind._levels == [0.1] * 5
    ind.set_state("finishing")
    ind.update_levels([0.2] * 5)
    assert ind._levels == [0.1] * 5
