"""Microphone capture: open at the device's native rate, deliver 16 kHz mono.

The stream is opened when dictation starts and closed when it stops, so the
Windows mic-in-use indicator is only lit while you're dictating.
"""

import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import soxr

from . import audio_devices


class AudioRecorder:
    TARGET_RATE = 16000
    BLOCK_SECONDS = 0.03
    _LEVEL_HISTORY = 60

    def __init__(self, device_ref=None, stream_factory: Optional[Callable] = None,
                 resolver: Optional[Callable] = None):
        self._device_ref = device_ref
        self._stream_factory = stream_factory or sd.InputStream
        self._resolver = resolver or audio_devices.resolve
        self._stream = None
        self._resampler: Optional[soxr.ResampleStream] = None
        self._recording = False
        self._stopping = False
        self._chunks: list[np.ndarray] = []
        self._read_pos = 0
        self._lock = threading.Lock()
        self._levels: list[float] = []
        self._level_lock = threading.Lock()
        self.stream_error: Optional[str] = None

    # -- stream callbacks (PortAudio thread) ---------------------------------

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata.mean(axis=1) if indata.shape[1] > 1 else indata[:, 0]
        mono = np.ascontiguousarray(mono, dtype=np.float32)
        if len(mono):
            # Measured before resampling: the resampler buffers its first chunks.
            level = float(np.sqrt(np.mean(mono ** 2)))
            with self._level_lock:
                self._levels.append(level)
                del self._levels[:-self._LEVEL_HISTORY]
        if self._resampler is not None:
            mono = self._resampler.resample_chunk(mono)
        if len(mono):
            with self._lock:
                if self._recording:
                    self._chunks.append(mono.copy())

    def _on_finished(self) -> None:
        if self._recording and not self._stopping:
            self.stream_error = "The microphone stopped unexpectedly"

    # -- open / close ----------------------------------------------------------

    def _open(self, index: int):
        info = sd.query_devices(index, "input")
        channels = max(1, min(int(info["max_input_channels"]), 2))
        native = int(info["default_samplerate"])
        common = dict(device=index, channels=channels, dtype="float32",
                      callback=self._callback, finished_callback=self._on_finished)
        try:
            stream = self._stream_factory(samplerate=native,
                                          blocksize=int(native * self.BLOCK_SECONDS), **common)
            rate = native
        except sd.PortAudioError:
            if "WASAPI" not in sd.query_hostapis(info["hostapi"])["name"]:
                raise
            stream = self._stream_factory(
                samplerate=self.TARGET_RATE,
                blocksize=int(self.TARGET_RATE * self.BLOCK_SECONDS),
                extra_settings=sd.WasapiSettings(auto_convert=True), **common)
            rate = self.TARGET_RATE
        self._resampler = (soxr.ResampleStream(rate, self.TARGET_RATE, 1, dtype="float32")
                           if rate != self.TARGET_RATE else None)
        return stream

    def start_recording(self) -> None:
        """Open the configured device and start capturing. Raises on failure."""
        with self._lock:
            self._chunks = []
            self._read_pos = 0
        with self._level_lock:
            self._levels.clear()
        self.stream_error = None
        self._stopping = False
        try:
            index = self._resolver(self._device_ref)
        except audio_devices.DeviceNotFoundError:
            audio_devices.refresh()  # it may have appeared since PortAudio last scanned
            index = self._resolver(self._device_ref)
        stream = self._open(index)
        self._stream = stream
        self._recording = True
        try:
            stream.start()
        except Exception:
            self._recording = False
            self._stream = None
            stream.close()
            raise

    def stop_recording(self) -> Optional[np.ndarray]:
        """Close the stream and return everything captured as 16 kHz float32."""
        self._stopping = True
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        with self._lock:
            self._recording = False
            if self._resampler is not None:
                tail = self._resampler.resample_chunk(np.zeros(0, np.float32), last=True)
                if len(tail):
                    self._chunks.append(tail)
            chunks, self._chunks = self._chunks, []
        self._resampler = None
        if not chunks:
            return None
        return np.concatenate(chunks).astype(np.float32)

    def read_new(self) -> np.ndarray:
        """16 kHz audio captured since the previous call (for live decoding)."""
        with self._lock:
            fresh = self._chunks[self._read_pos:]
            self._read_pos = len(self._chunks)
        return np.concatenate(fresh) if fresh else np.zeros(0, np.float32)

    # -- levels -----------------------------------------------------------------

    def get_levels(self, count: int = 30) -> list[float]:
        with self._level_lock:
            history = list(self._levels)
        if len(history) >= count:
            return history[-count:]
        return [0.0] * (count - len(history)) + history

    @property
    def is_recording(self) -> bool:
        return self._recording
