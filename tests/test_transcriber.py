"""Tests for transcriber compute selection and segment joining."""

from types import SimpleNamespace

import numpy as np
import pytest

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


def test_transcribe_words_is_greedy_and_split():
    t = loaded([" Hello there,", " friend."])
    assert t.transcribe_words(np.zeros(16000, np.float32)) == ["Hello", "there,", "friend."]
    assert t._model.kwargs["beam_size"] == 1
    assert t._model.kwargs["vad_filter"] is False


def test_auto_model_depends_on_live_on_cpu():
    assert tr.resolve_model_size("auto", "cpu", live=True) == "base"
    assert tr.resolve_model_size("auto", "cpu", live=False) == "small"
    assert tr.resolve_model_size("auto", "cuda", live=True) == "large-v3-turbo"


@pytest.mark.parametrize("pref,device,live", [
    ("auto", "cuda", True), ("auto", "cpu", False), ("on", "cpu", True), ("off", "cuda", False),
])
def test_live_decided_from_preference_and_device(monkeypatch, pref, device, live):
    monkeypatch.setattr(tr, "WhisperModel", lambda *a, **k: object())
    t = tr.Transcriber(model_size="auto", live_typing=pref, device=device, compute_type="int8")
    t.load_model()
    assert t.live is live


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


def test_only_complete_runtime_folders_are_searched(monkeypatch, tmp_path):
    complete = tmp_path / "cuda" / "cublas-1_cudnn-1"
    complete.mkdir(parents=True)
    (complete / tr.RUNTIME_MARKER).write_text("{}")
    (tmp_path / "cuda" / "cublas-2_cudnn-2.partial").mkdir()
    monkeypatch.setattr(tr, "runtime_dir", lambda: str(tmp_path / "cuda"))
    dirs = tr._nvidia_dll_dirs()
    assert str(complete) in dirs
    assert not any(d.endswith(".partial") for d in dirs)


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
    monkeypatch.setattr(tr, "_gpu_compute_type", lambda: "int8_float16")
    assert tr.select_compute() == ("cuda", "int8_float16")


def test_gpu_compute_type_falls_back_to_float16(monkeypatch):
    import ctranslate2
    monkeypatch.setattr(ctranslate2, "get_supported_compute_types", lambda device: {"float16", "float32"})
    assert tr._gpu_compute_type() == "float16"
    monkeypatch.setattr(ctranslate2, "get_supported_compute_types",
                        lambda device: {"float16", "int8_float16", "int8"})
    assert tr._gpu_compute_type() == "int8_float16"


def test_cuda_failure_during_transcribe_retries_on_cpu(monkeypatch):
    class Broken:
        def transcribe(self, audio, **kwargs):
            raise RuntimeError("CUDA failed with error out of memory")
    monkeypatch.setattr(tr, "WhisperModel", lambda *a, **k: FakeModel([" Hello."]))
    monkeypatch.setattr(tr, "_bundled_model_path", lambda size: None)
    t = tr.Transcriber(model_size="auto", device="cuda", compute_type="float16")
    t._model = Broken()
    assert t.transcribe(np.zeros(16000, np.float32)) == "Hello."
    assert t.device == "cpu" and t.model_size == "small"


def test_requested_reports_configuration():
    t = tr.Transcriber(model_size="auto", compute="cpu", live_typing="off")
    assert t.requested == ("auto", "cpu", "off")


def test_transcribe_words_with_timestamps():
    seg = SimpleNamespace(text=" Hi there.", words=[SimpleNamespace(word=" Hi", end=0.4),
                                                     SimpleNamespace(word=" there.", end=0.9)])
    t = tr.Transcriber(model_size="base", device="cpu", compute_type="int8")
    t._model = type("M", (), {"transcribe": lambda self, audio, **kw: (iter([seg]), None)})()
    assert t.transcribe_words(np.zeros(16000, np.float32), timestamps=True) == [("Hi", 0.4), ("there.", 0.9)]
