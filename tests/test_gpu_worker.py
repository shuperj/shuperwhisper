"""RemoteTranscriber's plumbing, with the helper served from a thread."""

import multiprocessing
import threading

import pytest

from shuper_whisper import gpu_worker
from shuper_whisper.gpu_worker import RemoteTranscriber


class FakeTranscriber:
    def __init__(self, model_size="auto", language="en", compute="auto", live_typing="auto"):
        self.language, self.compute = language, compute
        self.device, self.model_size, self.live, self.loaded = None, model_size, False, False

    def load_model(self):
        self.device = "cpu" if self.compute == "cpu" else "cuda"
        self.model_size, self.live, self.loaded = "base.en", True, True

    def transcribe(self, audio, initial_prompt=None, hotwords=None):
        return f"heard {len(audio)} samples on {self.device}"

    def transcribe_words(self, audio, initial_prompt=None, hotwords=None, beam_size=1, timestamps=False):
        if audio == "boom":
            raise RuntimeError("CUDA failed")
        return ["hello", self.language, self.device]


class ThreadHelper:
    """Stands in for the process: _serve on a thread."""

    def __init__(self, thread):
        self.thread, self.killed = thread, False

    def join(self, timeout=None):
        self.thread.join(timeout)

    def is_alive(self):
        return self.thread.is_alive() and not self.killed

    def terminate(self):
        self.killed = True


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(gpu_worker, "Transcriber", FakeTranscriber)

    def spawn(kwargs):
        ours, theirs = multiprocessing.Pipe()
        thread = threading.Thread(target=gpu_worker._serve, args=(theirs, kwargs), daemon=True)
        thread.start()
        return ours, ThreadHelper(thread)
    r = RemoteTranscriber("auto", language="en", spawn=spawn)
    r.load_model()
    yield r
    r.close()


def test_calls_go_to_the_helper(remote):
    assert remote.device == "cuda" and remote.model_size == "base.en" and remote.live and remote.loaded
    assert remote.transcribe_words([0.0] * 4) == ["hello", "en", "cuda"]
    assert remote.transcribe([0.0] * 8) == "heard 8 samples on cuda"
    remote.language = "de"
    assert remote.transcribe_words([0.0]) == ["hello", "de", "cuda"]


def test_errors_come_back_as_errors(remote):
    with pytest.raises(RuntimeError, match="CUDA failed"):
        remote.transcribe_words("boom")
    assert remote.transcribe_words([0.0]) == ["hello", "en", "cuda"]  # the helper is still fine


def test_close_ends_the_helper(remote):
    process = remote._process
    remote.close()
    process.join(2)
    assert not process.is_alive() and not remote.loaded


def test_a_dead_helper_falls_back_to_the_processor(remote):
    remote._conn.close()              # the helper is gone
    assert remote.transcribe_words([0.0]) == ["hello", "en", "cpu"]
    assert remote.device == "cpu" and remote.loaded
