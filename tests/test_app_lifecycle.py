"""Lifecycle: failures land in STATE_ERROR and are recoverable."""

import numpy as np
import pytest

from shuper_whisper import app as app_mod
from shuper_whisper.config import AppConfig


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

    def get_levels(self, n):
        return [0.0] * n


class FakeTranscriber:
    def __init__(self, model_size="auto", language="en", compute="auto", fail=False):
        self.compute = compute
        self.fail = fail
        self.loaded = False
        self.language = language
        self.text = "hello world"

    def load_model(self):
        if self.fail:
            raise RuntimeError("model download failed")
        self.loaded = True

    def transcribe(self, audio, initial_prompt=None, hotwords=None):
        return self.text


class FakeHotkeys:
    def __init__(self, hotkey_str, on_start, on_stop):
        self.registered = False
        self.resets = 0

    def register(self):
        self.registered = True

    def unregister(self):
        self.registered = False

    def reset(self):
        self.resets += 1


class FakeOverlay:
    BAR_COUNT = 14
    is_visible = False

    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeInjector:
    def __init__(self):
        self.typed = []

    def inject(self, text):
        self.typed.append(text)
        return text


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(app_mod, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(app_mod, "HotkeyManager", FakeHotkeys)
    monkeypatch.setattr(app_mod, "RecordingOverlay", lambda **k: FakeOverlay())
    monkeypatch.setattr(app_mod.audio_devices, "migrate", lambda v: v)
    monkeypatch.setattr(app_mod, "save_config", lambda c: None)

    def _make(**cfg):
        a = app_mod.ShuperWhisperApp(AppConfig(**cfg))
        a.dictionary = app_mod.WordDictionary(path=str(tmp_path / "d.json"))
        a.injector = FakeInjector()
        states = []
        a.set_state_callback(states.append)
        a.states = states
        a._run_async = lambda fn, *args: fn(*args)  # run session finish inline
        return a
    return _make


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
    assert a.hotkey_manager.resets == 1


def test_recovers_by_picking_a_working_device(make_app):
    a = make_app()
    a.start()
    a.recorder.fail = True
    a._on_record_start()
    a.reload_config(AppConfig(input_device={"name": "Good Mic", "hostapi": None}))
    assert a.states[-1] == "idle" and a.error is None
    assert a.recorder.device_ref == {"name": "Good Mic", "hostapi": None}


def test_cpu_only_setting_reloads_model_on_cpu(make_app):
    a = make_app()
    a.start()
    a.reload_config(AppConfig(compute="cpu"))
    assert a.transcriber.compute == "cpu" and a.states[-2:] == ["loading", "idle"]


def test_device_change_does_not_reload_model(make_app):
    a = make_app()
    a.start()
    t = a.transcriber
    a.reload_config(AppConfig(input_device={"name": "Good Mic", "hostapi": None}))
    assert a.transcriber is t


def test_full_session_types_clean_text(make_app):
    a = make_app()
    a.start()
    a.transcriber.text = "Hello  there — friend..."
    a._on_record_start()
    a._on_record_stop()
    assert a.injector.typed == ["Hello there, friend"]
    assert a.states[-1] == "idle"


def test_silence_types_nothing(make_app):
    a = make_app()
    a.start()
    a.recorder.audio = np.zeros(16000, np.float32)
    a._on_record_start()
    a._on_record_stop()
    assert a.injector.typed == [] and a.states[-1] == "idle"


def test_second_start_while_finishing_is_ignored(make_app):
    a = make_app()
    a.start()
    a._session_lock.acquire()
    a._on_record_start()
    assert a.hotkey_manager.resets == 1
    assert "recording" not in a.states


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
