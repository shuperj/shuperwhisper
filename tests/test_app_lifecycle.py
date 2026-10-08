"""Lifecycle: failures land in STATE_ERROR and are recoverable; live and
type-on-stop sessions feed the writer and always release the session."""

import numpy as np
import pytest

from shuper_whisper import app as app_mod
from shuper_whisper.config import AppConfig
from shuper_whisper.streaming import Hypothesis


class FakeRecorder:
    def __init__(self, device_ref=None, fail=False):
        self.device_ref = device_ref
        self.fail = fail
        self.stream_error = None
        self.audio = np.full(16000, 0.1, np.float32)

    def start_recording(self):
        if self.fail:
            raise RuntimeError("Invalid sample rate")

    def stop_recording(self):
        return self.audio

    def read_new(self):
        return np.zeros(0, np.float32)

    def get_levels(self, n):
        return [0.0] * n

    def check_alive(self):
        return self.stream_error


class FakeTranscriber:
    def __init__(self, model_size="auto", language="en", compute="auto", live_typing="auto",
                 fail=False):
        self.compute = compute
        self.live_typing = live_typing
        self.requested = (model_size, compute, live_typing)
        self.device = "cuda"
        self.live = live_typing != "off"
        self.fail = fail
        self.loaded = False
        self.language = language
        self.text = "hello world"

    def needs_reload_for(self, language):
        return False

    def load_model(self):
        if self.fail:
            raise RuntimeError("model download failed")
        self.loaded = True

    def transcribe(self, audio, initial_prompt=None, hotwords=None):
        return self.text


class FakeHotkeys:
    def __init__(self, hotkey_str, on_start, on_stop, on_cancel=None, mode="tap"):
        self.hotkey = hotkey_str
        self.mode = mode
        self.registered = False
        self.resets = 0

    def register(self):
        self.registered = True

    def unregister(self):
        self.registered = False

    def reset(self):
        self.resets += 1


class FakeIndicator:
    BAR_COUNT = 5
    is_visible = False

    def __init__(self):
        self.errors = []

    def show_error(self, m):
        self.errors.append(m)

    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeWriter:
    field = None

    def __init__(self, **kw):
        self.updates = []
        self.blocked = False

    def begin(self, ignore_vks=(), trigger_vk=0):
        pass

    def update(self, stable, tentative, final=False):
        if self.blocked:
            from shuper_whisper._win32_keys import InjectionBlocked
            raise InjectionBlocked("blocked")
        self.updates.append((stable, tentative, final))

    def finish(self):
        pass


class FakeSession:
    """Emits scripted hypotheses on start; stop() runs on_finished."""
    script = []

    def __init__(self, transcriber, read_audio, on_hypothesis, on_finished, on_auto_stop, **kw):
        self.on_hypothesis, self.on_finished = on_hypothesis, on_finished
        self.on_auto_stop = on_auto_stop
        self.interval = kw.get("interval")

    def start(self):
        for h in FakeSession.script:
            self.on_hypothesis(h)

    def stop(self):
        self.on_finished(None)


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(app_mod, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(app_mod, "HotkeyManager", FakeHotkeys)
    monkeypatch.setattr(app_mod, "CaretIndicator", FakeIndicator)
    monkeypatch.setattr(app_mod, "LiveWriter", FakeWriter)
    monkeypatch.setattr(app_mod, "StreamingSession", FakeSession)
    monkeypatch.setattr(app_mod.audio_devices, "migrate", lambda v: v)
    monkeypatch.setattr(app_mod, "save_config", lambda c: None)
    monkeypatch.setattr(app_mod.uia, "warm_up", lambda: None)
    monkeypatch.setattr(app_mod.gpu_runtime, "cleanup", lambda: None)
    FakeSession.script = []

    def _make(**cfg):
        a = app_mod.ShuperWhisperApp(AppConfig(**cfg))
        a.dictionary = app_mod.WordDictionary(path=str(tmp_path / "d.json"))
        states = []
        a.set_state_callback(states.append)
        a.states = states
        a._run_async = lambda fn, *args: fn(*args)
        return a
    return _make


# -- lifecycle ------------------------------------------------------------------

def test_start_reaches_idle(make_app):
    a = make_app()
    a.start()
    assert a.states == ["loading", "idle"] and a.is_running


def test_model_failure_is_error_not_loading(make_app):
    a = make_app()
    a.transcriber.fail = True
    a.start()
    assert a.states[-1] == "error" and "model download failed" in a.error


def test_mic_failure_at_dictation_is_error_and_resets_hotkey(make_app):
    a = make_app()
    a.start()
    a.recorder.fail = True
    a._on_record_start()
    assert a.states[-1] == "error" and "Invalid sample rate" in a.error
    assert a.hotkey_manager.resets == 1 and a.overlay.errors
    assert not a.busy


def test_recovers_by_picking_a_working_device(make_app):
    a = make_app()
    a.start()
    a.recorder.fail = True
    a._on_record_start()
    a.reload_config(AppConfig(input_device={"name": "Good Mic", "hostapi": None}))
    assert a.states[-1] == "idle" and a.error is None
    assert a.recorder.device_ref == {"name": "Good Mic", "hostapi": None}


def test_cpu_only_setting_reloads_model(make_app):
    a = make_app()
    a.start()
    a.reload_config(AppConfig(compute="cpu"))
    assert a.transcriber.compute == "cpu" and a.states[-2:] == ["loading", "idle"]


def test_live_typing_change_reloads_model(make_app):
    a = make_app()
    a.start()
    a.reload_config(AppConfig(live_typing="off"))
    assert a.transcriber.live_typing == "off"


def test_device_change_does_not_reload_model(make_app):
    a = make_app()
    a.start()
    t = a.transcriber
    a.reload_config(AppConfig(input_device={"name": "Good Mic", "hostapi": None}))
    assert a.transcriber is t


def test_second_start_while_finishing_is_ignored(make_app):
    a = make_app()
    a.start()
    a._session_lock.acquire()
    a._on_record_start()
    assert a.hotkey_manager.resets == 1
    assert "recording" not in a.states


def test_reload_refused_while_dictating(make_app):
    a = make_app()
    a.start()
    a._on_record_start()
    recorder = a.recorder
    assert a.reload_config(AppConfig(hotkey="f9", input_device={"name": "X", "hostapi": None})) is False
    assert a.recorder is recorder and a.hotkey_manager.hotkey == "ctrl+shift+space"
    a._on_record_stop()
    assert not a.busy and a.states[-1] == "idle"


def test_failed_model_load_keeps_old_model_and_applies_the_rest(make_app, monkeypatch):
    a = make_app()
    a.start()
    old = a.transcriber
    monkeypatch.setattr(FakeTranscriber, "load_model",
                        lambda self: (_ for _ in ()).throw(RuntimeError("offline")))
    a.reload_config(AppConfig(hotkey="f9", model_size="small"))
    assert a.transcriber is old and "offline" in a.reload_error
    assert a.config.model_size == "auto" and a.config.hotkey == "f9"
    assert a.hotkey_manager.hotkey == "f9" and a.states[-1] == "idle"
    monkeypatch.setattr(FakeTranscriber, "load_model", lambda self: setattr(self, "loaded", True))
    a.reload_config(AppConfig(hotkey="f9", model_size="small"))
    assert a.config.model_size == "small" and a.reload_error is None


def test_background_reload_reports_loading_then_applies(make_app):
    a = make_app()
    a.start()
    done = []
    a.reload_in_background(AppConfig(model_size="small"), on_done=done.append)
    assert done == [True] and a.config.model_size == "small"
    assert a.states[-3:] == ["loading", "loading", "idle"]


def test_background_reload_waits_out_a_short_dictation(make_app):
    import threading
    a = make_app()
    a.start()
    a._run_async = lambda fn, *args: threading.Thread(target=fn, args=args).start()
    a._session_lock.acquire()
    done = threading.Event()
    a.reload_in_background(AppConfig(model_size="small"), on_done=lambda ok: done.set())
    threading.Timer(0.2, a._session_lock.release).start()
    assert done.wait(5) and a.config.model_size == "small"

def test_legacy_device_index_migrated_on_start(make_app, monkeypatch):
    saved = []
    monkeypatch.setattr(app_mod.audio_devices, "migrate",
                        lambda v: {"name": "B1", "hostapi": "Windows WASAPI"} if v == 75 else v)
    monkeypatch.setattr(app_mod, "save_config", saved.append)
    a = make_app(input_device=75)
    a.start()
    assert a.config.input_device == {"name": "B1", "hostapi": "Windows WASAPI"}
    assert a.recorder.device_ref == a.config.input_device
    assert saved


# -- live sessions ----------------------------------------------------------------

def test_live_session_feeds_writer_and_returns_to_idle(make_app):
    a = make_app()
    a.start()
    FakeSession.script = [Hypothesis("", "hello", False), Hypothesis("hello world.", "", True)]
    a._on_record_start()
    assert a.writer.updates == [("", "hello", False), ("hello world.", "", True)]
    assert a.states[-1] == "recording"
    a._on_record_stop()
    assert a.states[-2:] == ["processing", "idle"]
    assert not a.busy


def test_blocked_typing_stops_session_with_error(make_app):
    a = make_app()
    a.start()
    FakeSession.script = [Hypothesis("hi", "", True)]
    a.writer.blocked = True
    a._on_record_start()          # writer raises -> session stops itself
    assert a.states[-1] == "error" and a.overlay.errors == ["blocked"]
    assert a.hotkey_manager.resets >= 1 and not a.busy


def test_auto_stop_resets_hotkey_and_finishes(make_app):
    a = make_app()
    a.start()
    a._on_record_start()
    a._session.on_auto_stop()
    assert a.hotkey_manager.resets >= 1 and a.states[-1] == "idle"


def test_cpu_uses_slower_interval(make_app):
    a = make_app()
    a.start()
    a.transcriber.device = "cpu"
    a._on_record_start()
    assert a._session.interval == 1.0


def test_dead_microphone_ends_session(make_app):
    a = make_app()
    a.start()
    a.overlay.is_visible = True
    a._on_record_start()
    a.recorder.stream_error = "The microphone stopped sending audio"
    a._start_level_monitoring(a._current)
    assert a.states[-1] == "error" and "stopped" in a.error
    assert not a.busy


# -- type-on-stop sessions ----------------------------------------------------------

def test_type_on_stop_writes_once(make_app):
    a = make_app()
    a.start()
    a.transcriber.live = False
    a.transcriber.text = "hello  world — again"
    a._on_record_start()
    assert a._session is None and a.states[-1] == "recording"
    a._on_record_stop()
    assert a.writer.updates == [("hello  world — again", "", True)]  # LiveWriter cleans it
    assert a.states[-1] == "idle" and not a.busy


def test_type_on_stop_silence_writes_nothing(make_app):
    a = make_app()
    a.start()
    a.transcriber.live = False
    a.recorder.audio = np.zeros(16000, np.float32)
    a._on_record_start()
    a._on_record_stop()
    assert a.writer.updates == [] and a.states[-1] == "idle"


def test_cancel_takes_back_live_words(make_app):
    a = make_app()
    a.start()
    FakeSession.script = [Hypothesis("", "hello", False)]
    a._on_record_start()
    a._on_record_cancel()                       # a lone tap in double-tap mode
    assert a.writer.updates == [("", "hello", False), ("", "", True)]
    assert a.states[-1] == "idle" and not a.busy


def test_cancel_type_on_stop_types_nothing(make_app):
    a = make_app()
    a.start()
    a.transcriber.live = False
    a.transcriber.text = "hello"
    a._on_record_start()
    a._on_record_cancel()
    assert a.writer.updates == [("", "", True)]  # clearing an empty tail types nothing
    assert a.states[-1] == "idle" and not a.busy


def test_shortcut_mode_applies_without_reregistering(make_app):
    a = make_app()
    a.start()
    keys = a.hotkey_manager
    assert a.reload_config(AppConfig(shortcut="double"))
    assert a.hotkey_manager is keys and keys.mode == "double" and a.config.shortcut == "double"


def test_is_silent_uses_loudest_window():
    quiet_then_word = np.zeros(16000 * 20, np.float32)
    quiet_then_word[16000:17600] = 0.05   # 100 ms of speech in 20 s
    assert app_mod.is_silent(quiet_then_word) is False
    assert app_mod.is_silent(np.full(16000, 0.001, np.float32)) is True
    assert app_mod.is_silent(None) is True


def test_force_model_reload(make_app):
    a = make_app()
    a.start()
    t = a.transcriber
    a.reload_config(a.config, force_model=True)
    assert a.transcriber is not t


def test_state_tracked(make_app):
    a = make_app()
    a.start()
    assert a.state == "idle"

def test_late_stop_after_session_ended_is_ignored(make_app):
    a = make_app()
    a.start()
    FakeSession.script = [Hypothesis("hi", "", True)]
    a._on_record_start()
    token = a._current
    a._auto_stop(token)                      # session ends by itself
    assert not a.busy and a.states[-1] == "idle"
    a._on_record_stop()                       # the user's (late) stop press
    a._on_record_stop(token)                  # and a stale dead-mic stop
    assert not a.busy and a.states[-1] == "idle"
    a._on_record_start()                      # next dictation still works
    assert a.busy and a.states[-1] == "recording"


def test_double_stop_releases_once(make_app):
    a = make_app()
    a.start()
    a.transcriber.live = False
    a._on_record_start()
    a._on_record_stop()
    a._on_record_stop()
    assert not a.busy and a.states.count("processing") == 1


def test_start_failure_after_mic_opened_releases_session(make_app, monkeypatch):
    a = make_app()
    a.start()
    monkeypatch.setattr(a.writer, "begin", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    a._on_record_start()
    assert not a.busy and a.states[-1] == "error" and "boom" in a.error
