"""Audio recording using sounddevice."""

import threading
from typing import Optional

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """Manages audio input stream and recording state."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCKSIZE = 1024

    def __init__(self, device: Optional[object] = None):
        self._device = device
        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._audio_data: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._open_channels = self.CHANNELS
        # Level monitoring for waveform visualization
        self._level_history: list[float] = []
        self._level_lock = threading.Lock()

    def _audio_callback(self, indata, frames, time_info, status):
        # Mix down to mono if device was opened with multiple channels
        mono = indata.mean(axis=1, keepdims=True) if indata.shape[1] > 1 else indata
        if self._recording:
            self._audio_data.append(mono.copy())
        # Always compute RMS level for visualization
        rms = float(np.sqrt(np.mean(mono ** 2)))
        with self._level_lock:
            self._level_history.append(rms)
            # Keep ~2 seconds of history at callback rate (~15 callbacks/sec)
            if len(self._level_history) > 60:
                self._level_history = self._level_history[-60:]

    def open_stream(self) -> None:
        """Open the audio input stream.

        Some devices (Bluetooth headsets, certain USB interfaces) are stereo-only
        and reject mono (1-channel) requests with paInvalidChannelCount. Query the
        device's max channels and open with up to 2; the callback mixes down to mono.
        """
        device_info = sd.query_devices(self._device, "input")
        self._open_channels = max(1, min(int(device_info["max_input_channels"]), 2))
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self._open_channels,
            callback=self._audio_callback,
            blocksize=self.BLOCKSIZE,
            device=self._device,
        )
        self._stream.start()

    def close_stream(self) -> None:
        """Stop and close the audio input stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def start_recording(self) -> None:
        """Begin capturing audio frames."""
        with self._lock:
            self._recording = True
            self._audio_data = []
        with self._level_lock:
            self._level_history.clear()

    def stop_recording(self) -> Optional[np.ndarray]:
        """Stop capturing and return the recorded audio as a flat float32 array.

        Returns None if no audio was captured.
        """
        with self._lock:
            self._recording = False
            captured = self._audio_data.copy()
            self._audio_data = []
        if not captured:
            return None
        return np.concatenate(captured, axis=0).flatten().astype(np.float32)

    def get_levels(self, count: int = 30) -> list[float]:
        """Return the most recent RMS levels for waveform display.

        Returns exactly `count` values, resampled from history.
        """
        with self._level_lock:
            history = self._level_history.copy()

        if not history:
            return [0.0] * count

        if len(history) >= count:
            # Take the most recent `count` values
            return history[-count:]

        # Pad with zeros on the left if not enough history
        padding = [0.0] * (count - len(history))
        return padding + history

    @property
    def is_recording(self) -> bool:
        return self._recording

    @staticmethod
    def list_devices() -> list[dict]:
        """Return a list of available audio input devices."""
        devices = sd.query_devices()
        result = []
        default_idx = sd.default.device[0]
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                result.append(
                    {
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "sample_rate": dev["default_samplerate"],
                        "is_default": i == default_idx,
                    }
                )
        return result

    @staticmethod
    def get_default_device_name() -> str:
        """Return the name of the default input device."""
        default_device = sd.query_devices(sd.default.device[0])
        return default_device["name"]
