"""Bridge calls used by the redesigned settings page."""

import threading
from unittest.mock import MagicMock

import pytest

from shuper_whisper import bridge as bridge_mod
from shuper_whisper.bridge import WindowAPI
from shuper_whisper.config import AppConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    app = MagicMock()
    app.state, app.error, app.busy = "idle", None, False
    app.transcriber.device = "cuda"
    app.transcriber.model_size = "large-v3-turbo"
    app.config = AppConfig()
    app.reload_config.return_value = True
    a = WindowAPI()
    a.set_app_instance(app)
    monkeypatch.setattr("shuper_whisper.config._default_config_path",
                        lambda: str(tmp_path / "config.json"))
    return a


def test_status(api):
    api._app.state, api._app.error = "error", "Mic gone"
    assert api.get_status() == {"state": "error", "error": "Mic gone"}


def test_system_info(api, monkeypatch):
    monkeypatch.setattr(bridge_mod.system_theme, "apps_use_dark", lambda: True)
    monkeypatch.setattr(bridge_mod.system_theme, "accent_colors",
                        lambda: {"light": "#0067c0", "dark": "#4cc2ff"})
    monkeypatch.setattr(bridge_mod, "gpu_name", lambda: "NVIDIA GeForce RTX 3080")
    info = api.get_system_info()
    assert info["dark"] is True
    assert info["compute"] == "Large v3 Turbo on NVIDIA GeForce RTX 3080"


def test_cpu_compute_label(api, monkeypatch):
    api._app.transcriber.device = "cpu"
    api._app.transcriber.model_size = "base"
    monkeypatch.setattr(bridge_mod, "gpu_name", lambda: None)
    assert api.get_system_info()["compute"] == "Base on CPU"


def test_model_change_reloads_in_background_then_saves(api, tmp_path):
    started = threading.Event()

    def reload(config):
        started.set()
        return True
    api._app.reload_config.side_effect = reload
    result = api.save_config({"model_size": "small"})
    assert result["success"] and result["loading"]
    assert started.wait(2)
    for _ in range(50):
        if (tmp_path / "config.json").exists():
            break
        threading.Event().wait(0.02)
    assert '"small"' in (tmp_path / "config.json").read_text()


def test_hotkey_change_applies_synchronously(api):
    result = api.save_config({"hotkey": "f9"})
    assert result["success"] and not result.get("loading")
    api._app.reload_config.assert_called_once()


def test_failed_apply_is_not_saved(api, tmp_path):
    api._app.error = "Couldn't register 'f9'"
    result = api.save_config({"hotkey": "f9"})
    assert result == {"success": False, "error": "Couldn't register 'f9'"}
    assert not (tmp_path / "config.json").exists()


def test_busy_refuses(api):
    api._app.busy = True
    assert "Finish dictating" in api.save_config({"hotkey": "f9"})["error"]


def test_gpu_status(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "gpu_name", lambda: "NVIDIA GeForce RTX 3080")
    monkeypatch.setattr(bridge_mod.gpu_runtime, "installed", lambda: False)
    assert api.get_gpu_status() == {"gpu": "NVIDIA GeForce RTX 3080", "installed": False, "active": True}


def test_gpu_setup_success_reloads_model(api, monkeypatch):
    class FakeSetup:
        progress = bridge_mod.gpu_runtime.Progress(state="done", message="ok")

        def start(self, on_done=None):
            on_done("done")
    monkeypatch.setattr(bridge_mod, "_gpu_setup", FakeSetup())
    assert api.setup_gpu() == {"success": True}
    api._app.reload_config.assert_called_once_with(api._app.config, force_model=True)
    assert api.get_gpu_setup_progress()["state"] == "done"


class FakeRecorder:
    def __init__(self, device_ref=None):
        self.device_ref = device_ref
        self.stopped = False

    def start_recording(self):
        if self.device_ref == {"name": "Broken", "hostapi": None}:
            raise RuntimeError("Invalid sample rate")

    def get_levels(self, n):
        return [0.0] * (n - 1) + [0.2]

    def stop_recording(self):
        self.stopped = True


def test_mic_test_round_trip(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "AudioRecorder", FakeRecorder)
    assert api.start_mic_test({"name": "B1", "hostapi": None}) == {"success": True}
    assert api.get_mic_level() == pytest.approx(0.2)
    recorder = api._mic_test
    api.stop_mic_test()
    assert recorder.stopped and api._mic_test is None


def test_mic_test_error(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "AudioRecorder", FakeRecorder)
    result = api.start_mic_test({"name": "Broken", "hostapi": None})
    assert result == {"success": False, "error": "Invalid sample rate"}
    assert api.get_mic_level() == 0.0
