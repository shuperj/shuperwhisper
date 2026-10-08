"""Speech-to-text transcription using faster-whisper."""

import ctypes
import functools
import os
import subprocess
import sys
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

# ctranslate2 >= 4.5 is built against CUDA 12 + cuDNN 9.
_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")
_added_dll_dirs: set[str] = set()
# Written last by gpu_runtime.install(): a runtime folder without it is incomplete.
RUNTIME_MARKER = "runtime.json"


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
    """Where the GPU runtime downloader keeps its versioned CUDA folders.

    Next to the exe when installed; a separate folder when running from
    source, so a dev checkout never shares (or loses) the installed copy's.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "cuda")
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(base, "ShuperWhisperDev", "cuda")


def _complete_runtime() -> Optional[str]:
    """Newest fully installed runtime folder (one with the marker), if any."""
    base = runtime_dir()
    try:
        folders = [os.path.join(base, n) for n in os.listdir(base)]
    except OSError:
        return None
    complete = [f for f in folders if os.path.isfile(os.path.join(f, RUNTIME_MARKER))]
    return max(complete, key=os.path.getmtime) if complete else None


@functools.lru_cache(maxsize=1)
def gpu_name() -> Optional[str]:
    """Name of the first NVIDIA GPU, via nvidia-smi (None if unavailable)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW)
        name = out.stdout.strip().splitlines()[0].strip()
        return name or None
    except Exception:
        return None


def _cuda_device_count() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def _nvidia_dll_dirs() -> list[str]:
    """The downloaded GPU runtime, plus the bin/ folders of the pip
    nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels (dev installs)."""
    runtime = _complete_runtime()
    dirs = [runtime] if runtime else []
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
        if path in _added_dll_dirs:
            continue
        _added_dll_dirs.add(path)
        os.add_dll_directory(path)
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
    try:
        for dll in _CUDA_DLLS:
            ctypes.WinDLL(dll)
        return True
    except OSError:
        return False


def _gpu_compute_type() -> str:
    try:
        import ctranslate2
        supported = ctranslate2.get_supported_compute_types("cuda")
    except Exception:
        return "float16"
    return "int8_float16" if "int8_float16" in supported else "float16"


def select_compute(preference: str = "auto") -> tuple[str, str]:
    """("cuda", "int8_float16") when a usable NVIDIA GPU is present, else CPU int8.

    int8 weights halve the VRAM (large-v3-turbo: 1.2 GB instead of 2.4 GB)
    at the same speed and, in our tests, the same text. GPUs without int8
    support get float16.

    preference="cpu" (the "Use GPU when available" setting turned off) or
    SHUPER_WHISPER_DEVICE=cpu forces CPU without probing CUDA at all.
    """
    if preference == "cpu" or os.environ.get("SHUPER_WHISPER_DEVICE", "").lower() == "cpu":
        return ("cpu", "int8")
    if _cuda_device_count() > 0 and _load_cuda_dlls():
        return ("cuda", _gpu_compute_type())
    return ("cpu", "int8")


def resolve_model_size(model_size: str, device: str, live: bool = False, language: str = "en") -> str:
    """"auto" is Base on any device: in the benchmark on the user's own voice
    it was close to the large models at a fraction of the memory, and fast
    enough for live typing on a CPU. English gets the English-only base.en
    (2.3% vs 4.3% wrong words live)."""
    if model_size != "auto":
        return model_size
    return "base.en" if language == "en" else "base"


class Transcriber:
    """Wraps faster-whisper's WhisperModel."""

    def __init__(self, model_size: str = "auto", language: str = "en", compute: str = "auto",
                 live_typing: str = "auto",
                 device: Optional[str] = None, compute_type: Optional[str] = None):
        self._compute_pref = compute
        self._live_pref = live_typing
        self._live = False
        self._requested_size = model_size
        self._model_size = model_size
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def _configure(self, device: str, compute_type: str) -> str:
        """Fix device, precision and model size; return the model source."""
        self._device, self._compute_type = device, compute_type
        self._live = self._live_pref == "on" or (self._live_pref == "auto" and device == "cuda")
        self._model_size = resolve_model_size(self._requested_size, device, self._live, self._language)
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
            self._fall_back_to_cpu()

    def _fall_back_to_cpu(self) -> None:
        source = self._configure("cpu", "int8")
        self._model = WhisperModel(source, device="cpu", compute_type="int8")

    def _run_model(self, audio: np.ndarray, kwargs: dict) -> list:
        """Run the model; a CUDA failure mid-session (another app grabbed the
        VRAM, driver reset...) reloads on CPU and retries once."""
        try:
            segments, _info = self._model.transcribe(audio, **kwargs)
            return list(segments)
        except Exception as e:
            if self._device != "cuda":
                raise
            print(f"GPU transcription failed ({e}); switching to CPU")
            self._fall_back_to_cpu()
            segments, _info = self._model.transcribe(audio, **kwargs)
            return list(segments)

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
        segments = self._run_model(audio, kwargs)
        # Segment texts carry their own leading space; strip and re-join so
        # boundaries get exactly one.
        return " ".join(t for t in (s.text.strip() for s in segments) if t)

    def transcribe_words(self, audio: np.ndarray, initial_prompt: Optional[str] = None,
                         hotwords: Optional[str] = None, beam_size: int = 1,
                         timestamps: bool = False) -> list:
        """Fast pass for live dictation: words of the whole buffer.

        Returns words, or (word, end_seconds) pairs with ``timestamps=True``.
        No VAD filter here -- StreamingSession already segments by speech.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        kwargs = {
            "beam_size": beam_size,
            "language": None if self._language == "auto" else self._language,
            "vad_filter": False,
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        if hotwords:
            kwargs["hotwords"] = hotwords
        if timestamps:
            kwargs["word_timestamps"] = True
            segments = self._run_model(audio, kwargs)
            return [(w.word.strip(), float(w.end)) for s in segments for w in (s.words or [])
                    if w.word.strip()]
        segments = self._run_model(audio, kwargs)
        return " ".join(s.text.strip() for s in segments).split()

    @property
    def live(self) -> bool:
        return self._live

    @property
    def requested(self) -> tuple[str, str, str]:
        """(model size, compute, live typing) as configured, before "auto" resolves."""
        return self._requested_size, self._compute_pref, self._live_pref

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

    def close(self) -> None:
        """Nothing to end: the model is freed with the object. (The helper
        process version, gpu_worker.RemoteTranscriber, ends its process.)"""

    def needs_reload_for(self, language: str) -> bool:
        """Would "auto" pick a different model for ``language`` (base.en
        only speaks English)?"""
        return (self._requested_size == "auto" and self._device is not None
                and resolve_model_size("auto", self._device, self._live, language) != self._model_size)

    @language.setter
    def language(self, value: str) -> None:
        self._language = value
