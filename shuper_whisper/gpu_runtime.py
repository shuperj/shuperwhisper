"""NVIDIA CUDA runtime for GPU (live) dictation, downloaded on demand.

Too big to bundle (~1.3 GB), so the installer offers it when it finds an
NVIDIA card (it runs ``ShuperWhisper.exe --setup-gpu``) and Settings has a
button for later. The wheels come from PyPI, pinned by version and SHA-256,
and only their DLLs are kept, in transcriber.runtime_dir().
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable, NamedTuple, Optional

from .transcriber import runtime_dir


class Wheel(NamedTuple):
    name: str
    version: str
    url: str
    sha256: str
    size: int


# Must match the pyproject `gpu` extra. When ctranslate2 is upgraded, re-pin
# both from https://pypi.org/pypi/<name>/<version>/json (the win_amd64 file).
WHEELS = (
    Wheel("nvidia-cublas-cu12", "12.9.2.10",
          "https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
          "623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661", 553162896),
    Wheel("nvidia-cudnn-cu12", "9.27.0.42",
          "https://files.pythonhosted.org/packages/aa/38/f856579877f7c1c5066e61182e7de7bc27bf35a78c8d1b0fa592e6985bc4/nvidia_cudnn_cu12-9.27.0.42-py3-none-win_amd64.whl",
          "06e9b0026f3bad97d2b58666330fabec04fe1672f776661ecb0ce0029c27f142", 743068852),
)
MIN_DRIVER = (527, 41)  # oldest Windows driver that runs CUDA 12
_CHUNK = 1 << 20


class SetupError(RuntimeError):
    """Something the user can act on (driver too old, network, corrupt file)."""


class SetupCancelled(Exception):
    pass


def driver_version() -> Optional[tuple[int, int]]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW).stdout
        major, minor = out.strip().splitlines()[0].split(".")[:2]
        return int(major), int(minor)
    except Exception:
        return None


def _expected() -> dict[str, str]:
    return {w.name: w.version for w in WHEELS}


def installed(target: Optional[str] = None) -> bool:
    try:
        with open(os.path.join(target or runtime_dir(), "runtime.json"), encoding="utf-8") as f:
            return json.load(f).get("wheels") == _expected()
    except (OSError, ValueError):
        return False


@dataclass
class Progress:
    state: str = "idle"  # idle | downloading | extracting | done | error | cancelled
    done_bytes: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        total = sum(w.size for w in WHEELS) or 1
        fraction = 1.0 if self.state == "done" else round(min(self.done_bytes / total, 1.0), 3)
        return {"state": self.state, "fraction": fraction, "message": self.message}


def _download(wheel: Wheel, path: str, progress: Progress, cancel: threading.Event, opener) -> None:
    digest = hashlib.sha256()
    try:
        with opener(wheel.url, timeout=60) as response, open(path, "wb") as out:
            while True:
                if cancel.is_set():
                    raise SetupCancelled()
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                progress.done_bytes += len(chunk)
    except OSError as e:
        raise SetupError(f"Download failed: {e}") from e
    if digest.hexdigest() != wheel.sha256:
        raise SetupError(f"The {wheel.name} download was corrupted. Please try again.")


def _extract_dlls(wheel_path: str, dest: str) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        for member in zf.namelist():
            parts = member.split("/")
            if len(parts) == 4 and parts[0] == "nvidia" and parts[2] == "bin" \
                    and parts[3].lower().endswith(".dll"):
                with zf.open(member) as src, open(os.path.join(dest, parts[3]), "wb") as dst:
                    shutil.copyfileobj(src, dst)


def install(progress: Progress, cancel: threading.Event, opener=urllib.request.urlopen,
            target: Optional[str] = None,
            check_driver: Optional[Callable[[], Optional[tuple[int, int]]]] = None) -> None:
    """Download, verify and unpack the runtime. Leaves ``target`` untouched on failure."""
    target = target or runtime_dir()
    driver = (check_driver or driver_version)()
    if driver is not None and driver < MIN_DRIVER:
        raise SetupError(f"Update your NVIDIA driver first (you have {driver[0]}.{driver[1]:02d}; "
                         f"{MIN_DRIVER[0]}.{MIN_DRIVER[1]} or newer is needed).")
    staging = target + ".partial"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for wheel in WHEELS:
                path = os.path.join(tmp, wheel.url.rsplit("/", 1)[-1])
                progress.state, progress.message = "downloading", f"Downloading {wheel.name}…"
                _download(wheel, path, progress, cancel, opener)
                progress.state, progress.message = "extracting", f"Unpacking {wheel.name}…"
                _extract_dlls(path, staging)
                os.remove(path)
        with open(os.path.join(staging, "runtime.json"), "w", encoding="utf-8") as f:
            json.dump({"wheels": _expected()}, f)
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    progress.state, progress.message = "done", "GPU acceleration is ready"


class GpuSetup:
    """Runs install() on a background thread; one at a time."""

    def __init__(self):
        self.progress = Progress()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, on_done: Optional[Callable[[str], None]] = None) -> None:
        if self.running:
            return
        self.progress = Progress(state="downloading", message="Starting…")
        self._cancel.clear()

        def _work():
            try:
                # Look urlopen up at call time (tests patch it).
                install(self.progress, self._cancel, opener=urllib.request.urlopen)
            except SetupCancelled:
                self.progress.state, self.progress.message = "cancelled", "Cancelled"
            except Exception as e:
                self.progress.state, self.progress.message = "error", str(e)
            if on_done:
                on_done(self.progress.state)

        self._thread = threading.Thread(target=_work, daemon=True, name="gpu-setup")
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
