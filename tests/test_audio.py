"""Tests for audio module with level monitoring."""

import numpy as np
import pytest

from shuper_whisper.audio import AudioRecorder


class TestAudioRecorderInit:
    def test_default_device(self):
        r = AudioRecorder()
        assert r._device is None

    def test_custom_device(self):
        r = AudioRecorder(device=3)
        assert r._device == 3

    def test_not_recording_initially(self):
        r = AudioRecorder()
        assert r.is_recording is False


class TestLevelMonitoring:
    def test_initial_levels_are_zero(self):
        r = AudioRecorder()
        levels = r.get_levels(10)
        assert len(levels) == 10
        assert all(l == 0.0 for l in levels)

    def test_get_levels_returns_requested_count(self):
        r = AudioRecorder()
        for count in [1, 5, 30, 60]:
            levels = r.get_levels(count)
            assert len(levels) == count

    def test_levels_populated_after_callback(self):
        r = AudioRecorder()
        # Simulate audio callback with known data
        fake_audio = np.ones((1024, 1), dtype=np.float32) * 0.5
        r._recording = True
        r._audio_callback(fake_audio, 1024, None, None)
        levels = r.get_levels(5)
        assert len(levels) == 5
        # The last level should be non-zero (RMS of 0.5 = 0.5)
        assert levels[-1] > 0

    def test_level_history_capped(self):
        r = AudioRecorder()
        fake_audio = np.ones((1024, 1), dtype=np.float32) * 0.1
        for _ in range(100):
            r._audio_callback(fake_audio, 1024, None, None)
        with r._level_lock:
            assert len(r._level_history) <= 60

    def test_levels_cleared_on_start_recording(self):
        r = AudioRecorder()
        fake_audio = np.ones((1024, 1), dtype=np.float32) * 0.1
        r._audio_callback(fake_audio, 1024, None, None)
        r.start_recording()
        with r._level_lock:
            assert len(r._level_history) == 0


class TestRecordingState:
    def test_start_clears_data(self):
        r = AudioRecorder()
        r._audio_data = [np.zeros(10)]
        r.start_recording()
        assert r.is_recording is True
        assert len(r._audio_data) == 0

    def test_stop_returns_none_when_empty(self):
        r = AudioRecorder()
        r.start_recording()
        result = r.stop_recording()
        assert result is None
        assert r.is_recording is False

    def test_stop_returns_concatenated_audio(self):
        r = AudioRecorder()
        r.start_recording()
        # Simulate callback adding data
        r._audio_data = [
            np.ones((100, 1), dtype=np.float32),
            np.ones((100, 1), dtype=np.float32) * 0.5,
        ]
        result = r.stop_recording()
        assert result is not None
        assert result.dtype == np.float32
        assert len(result) == 200
