"""Tests for AudioRecorder: native-rate open, resampling, WASAPI fallback."""

import numpy as np
import pytest
import sounddevice as sd

from shuper_whisper import audio as audio_mod
from shuper_whisper.audio import AudioRecorder


class FakeStream:
    def __init__(self, fail=False, **kwargs):
        if fail:
            raise sd.PortAudioError("Invalid sample rate", -9997)
        self.kwargs = kwargs
        self.started = self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        pass

    def close(self):
        self.closed = True

    def feed(self, block):
        self.kwargs["callback"](block, len(block), None, sd.CallbackFlags())


@pytest.fixture
def device_info(monkeypatch):
    info = {"max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 2}
    monkeypatch.setattr(audio_mod.sd, "query_devices", lambda *a, **k: info)
    monkeypatch.setattr(audio_mod.sd, "query_hostapis",
                        lambda i=None: {"name": "Windows WASAPI"})
    return info


def make(streams, fail_first=False):
    calls = {"n": 0}

    def factory(**kwargs):
        calls["n"] += 1
        s = FakeStream(fail=fail_first and calls["n"] == 1, **kwargs)
        streams.append(s)
        return s
    return AudioRecorder(device_ref=None, stream_factory=factory, resolver=lambda ref: 8)


def sine(rate, seconds, channels=2):
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


class TestOpen:
    def test_opens_at_native_rate_with_device_index(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        kw = streams[0].kwargs
        assert kw["samplerate"] == 48000 and kw["device"] == 8 and kw["channels"] == 2
        assert streams[0].started and r.is_recording

    def test_wasapi_fallback_uses_auto_convert(self, device_info):
        streams = []
        r = make(streams, fail_first=True)
        r.start_recording()
        kw = streams[-1].kwargs
        assert kw["samplerate"] == 16000
        assert kw["extra_settings"] is not None

    def test_non_wasapi_failure_raises(self, device_info, monkeypatch):
        from shuper_whisper import audio_devices
        monkeypatch.setattr(audio_devices, "refresh", lambda: False)  # can't rescan
        monkeypatch.setattr(audio_mod.sd, "query_hostapis", lambda i=None: {"name": "MME"})
        r = make([], fail_first=True)
        with pytest.raises(sd.PortAudioError):
            r.start_recording()
        assert not r.is_recording

    def test_missing_device_rescans_once(self, device_info, monkeypatch):
        from shuper_whisper import audio_devices
        refreshed = []
        monkeypatch.setattr(audio_devices, "refresh", lambda: refreshed.append(True) or True)
        attempts = {"n": 0}

        def resolver(ref):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise audio_devices.DeviceNotFoundError("B1 isn't connected")
            return 8
        r = AudioRecorder(device_ref={"name": "B1", "hostapi": None},
                          stream_factory=lambda **kw: FakeStream(**kw), resolver=resolver)
        r.start_recording()
        assert refreshed == [True] and r.is_recording


class TestCapture:
    def test_resamples_48k_stereo_to_16k_mono(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        block = sine(48000, 1.0)
        for i in range(0, len(block), 1440):
            streams[0].feed(block[i:i + 1440])
        audio = r.stop_recording()
        assert audio.dtype == np.float32 and audio.ndim == 1
        assert abs(len(audio) - 16000) < 400
        assert 0.15 < float(np.sqrt(np.mean(audio ** 2))) < 0.25
        assert streams[0].closed

    def test_stop_without_audio_returns_none(self, device_info):
        r = make([])
        r.start_recording()
        assert r.stop_recording() is None

    def test_levels(self, device_info):
        streams = []
        r = make(streams)
        assert r.get_levels(5) == [0.0] * 5
        r.start_recording()
        streams[0].feed(sine(48000, 0.03))
        assert r.get_levels(5)[-1] > 0

    def test_read_new_returns_only_fresh_audio(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        for _ in range(3):
            streams[0].feed(sine(48000, 0.1))
        first = r.read_new()
        assert abs(len(first) - 4800) < 600
        assert len(r.read_new()) == 0
        streams[0].feed(sine(48000, 0.3))
        assert len(r.read_new()) > 0

    def test_open_failure_rescans_and_retries(self, device_info, monkeypatch):
        from shuper_whisper import audio_devices
        monkeypatch.setattr(audio_devices, "refresh", lambda: True)
        monkeypatch.setattr(audio_mod.sd, "query_hostapis", lambda i=None: {"name": "MME"})
        streams = []
        r = make(streams, fail_first=True)
        r.start_recording()
        assert r.is_recording

    def test_stream_counter_tracks_open_streams(self, device_info):
        from shuper_whisper import audio_devices
        before = audio_devices._open_streams
        r = make([])
        r.start_recording()
        assert audio_devices._open_streams == before + 1
        r.stop_recording()
        assert audio_devices._open_streams == before

    def test_stall_detected(self, device_info):
        r = make([])
        r.start_recording()
        assert r.check_alive() is None
        r._last_callback -= 5
        assert "stopped" in r.check_alive()

    def test_unexpected_stream_end_sets_error(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        streams[0].kwargs["finished_callback"]()
        assert r.stream_error
