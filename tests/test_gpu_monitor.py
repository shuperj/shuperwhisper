"""Efficiency-mode detection, driven with made-up samples."""

from shuper_whisper.gpu_monitor import GIB, Detector, GpuMonitor


def test_big_memory_user_makes_it_busy_at_once():
    d = Detector()
    assert not d.update([("vivaldi.exe", 0.3 * GIB, 2.0)], now=0)
    assert d.update([("cyberpunk2077.exe", 6 * GIB, 95.0)], now=5)
    assert d.reason == "cyberpunk2077.exe"


def test_load_must_last_before_it_counts():
    d = Detector()
    game = [("game.exe", 1 * GIB, 80.0)]
    assert not d.update(game, now=0)
    assert not d.update(game, now=10)
    assert d.update(game, now=15)          # 15 s of sustained load
    assert d.reason == "game.exe"


def test_a_short_load_spike_is_ignored():
    d = Detector()
    assert not d.update([("video.exe", 0.2 * GIB, 90.0)], now=0)
    assert not d.update([("video.exe", 0.2 * GIB, 5.0)], now=5)
    assert not d.update([("video.exe", 0.2 * GIB, 90.0)], now=10)
    assert not d.update([("video.exe", 0.2 * GIB, 90.0)], now=20)  # restarted at 10 s
    assert d.update([("video.exe", 0.2 * GIB, 90.0)], now=25)


def test_clears_only_after_a_quiet_spell():
    d = Detector()
    d.update([("game.exe", 5 * GIB, 0.0)], now=0)
    assert d.update([], now=5)
    assert d.update([], now=30)
    assert not d.update([], now=36)         # 31 s after it went quiet
    assert d.reason == ""


def test_monitor_reports_changes_only():
    changes = []

    class Sampler:
        programs = []

        def sample(self):
            return self.programs

    t = [0.0]
    m = GpuMonitor(on_change=lambda busy, why: changes.append((busy, why)), clock=lambda: t[0])
    s = Sampler()
    m.check(s)
    s.programs = [("game.exe", 4 * GIB, 0.0)]
    t[0] = 5
    m.check(s)
    t[0] = 10
    m.check(s)
    s.programs = []
    t[0] = 50
    m.check(s)
    t[0] = 90
    m.check(s)
    assert changes == [(True, "game.exe"), (False, "")]
