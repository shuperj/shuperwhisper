"""Tests for transcriber compute selection and segment joining."""

from types import SimpleNamespace

import numpy as np

from shuper_whisper import transcriber as tr


class FakeModel:
    def __init__(self, texts):
        self.texts = texts
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter(SimpleNamespace(text=t) for t in self.texts), None


def loaded(texts, language="en"):
    t = tr.Transcriber(model_size="base", language=language, device="cpu", compute_type="int8")
    t._model = FakeModel(texts)
    return t


def test_joins_segments_with_single_spaces():
    t = loaded([" Hello there.", " How are you?", "  "])
    assert t.transcribe(np.zeros(16000, np.float32)) == "Hello there. How are you?"


def test_vad_and_language_passed():
    t = loaded([" Hi."], language="auto")
    t.transcribe(np.zeros(16000, np.float32), initial_prompt="Vocabulary: Dana.", hotwords="Dana")
    kw = t._model.kwargs
    assert kw["vad_filter"] is True
    assert kw["language"] is None
    assert kw["initial_prompt"] == "Vocabulary: Dana."
    assert kw["hotwords"] == "Dana"
    assert kw["condition_on_previous_text"] is False


def test_auto_model_size():
    assert tr.resolve_model_size("auto", "cuda") == "large-v3-turbo"
    assert tr.resolve_model_size("auto", "cpu") == "small"
    assert tr.resolve_model_size("base", "cuda") == "base"


def test_cpu_preference_never_probes_cuda(monkeypatch):
    def boom():
        raise AssertionError("probed CUDA")
    monkeypatch.delenv("SHUPER_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(tr, "_cuda_device_count", boom)
    assert tr.select_compute("cpu") == ("cpu", "int8")


def test_cuda_load_failure_falls_back_to_cpu(monkeypatch):
    calls = []

    def fake_model(source, device, compute_type):
        calls.append((source, device))
        if device == "cuda":
            raise RuntimeError("no kernel image is available for execution on the device")
        return object()
    monkeypatch.setattr(tr, "WhisperModel", fake_model)
    monkeypatch.setattr(tr, "_bundled_model_path", lambda size: None)
    t = tr.Transcriber(model_size="auto", device="cuda", compute_type="float16")
    t.load_model()
    assert calls == [("large-v3-turbo", "cuda"), ("small", "cpu")]
    assert t.device == "cpu" and t.model_size == "small"


def test_runtime_dir_is_searched(monkeypatch, tmp_path):
    (tmp_path / "cuda").mkdir()
    monkeypatch.setattr(tr, "runtime_dir", lambda: str(tmp_path / "cuda"))
    assert str(tmp_path / "cuda") in tr._nvidia_dll_dirs()


def test_select_compute_env_override(monkeypatch):
    monkeypatch.setenv("SHUPER_WHISPER_DEVICE", "cpu")
    assert tr.select_compute() == ("cpu", "int8")


def test_select_compute_falls_back_when_dlls_missing(monkeypatch):
    monkeypatch.delenv("SHUPER_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(tr, "_cuda_device_count", lambda: 1)
    monkeypatch.setattr(tr, "_load_cuda_dlls", lambda: False)
    assert tr.select_compute() == ("cpu", "int8")


def test_select_compute_uses_gpu_when_available(monkeypatch):
    monkeypatch.delenv("SHUPER_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(tr, "_cuda_device_count", lambda: 1)
    monkeypatch.setattr(tr, "_load_cuda_dlls", lambda: True)
    assert tr.select_compute() == ("cuda", "float16")
