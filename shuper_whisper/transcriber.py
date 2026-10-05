"""Speech-to-text transcription using faster-whisper."""

import ctypes
import os
import sys
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

# ctranslate2 >= 4.5 is built against CUDA 12 + cuDNN 9.
_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")


def _bundled_model_path(model_size: str) -> str | None:
    """Return the path to a bundled model if it exists alongside the exe."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "model", model_size)
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "model.bin")):
        return path
    return None


def runtime_dir() -> str:
    """Where the GPU runtime downloader puts the CUDA DLLs."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "cuda")
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(base, "ShuperWhisper", "cuda")


def _cuda_device_count() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def _nvidia_dll_dirs() -> list[str]:
    """The downloaded GPU runtime, plus the bin/ folders of the pip
    nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels (dev installs)."""
    dirs = [runtime_dir()] if os.path.isdir(runtime_dir()) else []
    roots = []
    try:
        import nvidia  # namespace package installed by the wheels
        roots.extend(nvidia.__path__)
    except ImportError:
        pass
    for root in roots:
        for lib in ("cublas", "cudnn"):
            path = os.path.join(root, lib, "bin")
            if os.path.isdir(path):
                dirs.append(path)
    return dirs


def _load_cuda_dlls() -> bool:
    """Make the CUDA runtime findable and prove it loads.

    ctranslate2 aborts the whole process (no exception) when it can't find
    cuDNN mid-inference, so this must succeed before we ever pick "cuda".
    """
    for path in _nvidia_dll_dirs():
        os.add_dll_directory(path)
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
    try:
        for dll in _CUDA_DLLS:
            ctypes.WinDLL(dll)
        return True
    except OSError:
        return False


def select_compute(preference: str = "auto") -> tuple[str, str]:
    """("cuda", "float16") when a usable NVIDIA GPU is present, else CPU int8.

    preference="cpu" (the "Use GPU when available" setting turned off) or
    SHUPER_WHISPER_DEVICE=cpu forces CPU without probing CUDA at all.
    """
    if preference == "cpu" or os.environ.get("SHUPER_WHISPER_DEVICE", "").lower() == "cpu":
        return ("cpu", "int8")
    if _cuda_device_count() > 0 and _load_cuda_dlls():
        return ("cuda", "float16")
    return ("cpu", "int8")


def resolve_model_size(model_size: str, device: str) -> str:
    if model_size != "auto":
        return model_size
    return "large-v3-turbo" if device == "cuda" else "small"


class Transcriber:
    """Wraps faster-whisper's WhisperModel."""

    def __init__(self, model_size: str = "auto", language: str = "en", compute: str = "auto",
                 device: Optional[str] = None, compute_type: Optional[str] = None):
        self._compute_pref = compute
        self._requested_size = model_size
        self._model_size = model_size
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _configure(self, device: str, compute_type: str) -> str:
        """Fix device, precision and model size; return the model source."""
        self._device, self._compute_type = device, compute_type
        self._model_size = resolve_model_size(self._requested_size, device)
        return _bundled_model_path(self._model_size) or self._model_size

    def load_model(self) -> None:
        if self._device is None:
            self._device, self._compute_type = select_compute(self._compute_pref)
        source = self._configure(self._device, self._compute_type)
        print(f"Loading Whisper {self._model_size} on {self._device} ({self._compute_type})")
        try:
            self._model = WhisperModel(source, device=self._device, compute_type=self._compute_type)
        except Exception as e:
            if self._device != "cuda":
                raise
            # Too-old GPU, out of VRAM, broken driver...: CPU still works.
            print(f"GPU model load failed ({e}); using CPU")
            source = self._configure("cpu", "int8")
            self._model = WhisperModel(source, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray, initial_prompt: Optional[str] = None,
                   hotwords: Optional[str] = None) -> str:
        """Transcribe 16 kHz mono float32 audio. Returns "" when nothing was said."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        kwargs = {
            "beam_size": 5,
            "language": None if self._language == "auto" else self._language,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        if hotwords:
            kwargs["hotwords"] = hotwords
        segments, _info = self._model.transcribe(audio, **kwargs)
        # Segment texts carry their own leading space; strip and re-join so
        # boundaries get exactly one.
        return " ".join(t for t in (s.text.strip() for s in segments) if t)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> Optional[str]:
        return self._device

    @property
    def model_size(self) -> str:
        return self._model_size

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = value
