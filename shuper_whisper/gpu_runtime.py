"""NVIDIA CUDA runtime for GPU (live) dictation, downloaded on demand.

Too big to bundle (~1.2 GB), so the installer offers it when it finds an
NVIDIA card (it runs ``ShuperWhisper.exe --setup-gpu``) and Settings has a
button for later. The wheels come from PyPI, pinned by version and SHA-256,
and only their DLLs are kept.

Each pinned set lives in its own folder under transcriber.runtime_dir(), so
a new version can be installed while the app has the old one loaded (Windows
can't delete loaded DLLs); old folders are removed at the next startup,
before CUDA is loaded.
"""

import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable, NamedTuple, Optional

from .transcriber import RUNTIME_MARKER, runtime_dir


class Wheel(NamedTuple):
    name: str
    version: str
    url: str
    sha256: str
    size: int


# Must match the pyproject `gpu` extra. cuDNN is pinned to the version the
# ctranslate2 wheel bundles its own cudnn64_9.dll from (4.8.2: 9.10.2.21), so
# its sub-libraries match. When ctranslate2 is upgraded, re-pin both from
# https://pypi.org/pypi/<name>/<version>/json (the win_amd64 file).
WHEELS = (
    Wheel("nvidia-cublas-cu12", "12.9.2.10",
          "https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fedbf1a385724393e505ed/nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl",
          "623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661", 553162896),
    Wheel("nvidia-cudnn-cu12", "9.10.2.21",
          "https://files.pythonhosted.org/packages/3d/90/0bd6e586701b3a890fd38aa71c387dab4883d619d6e5ad912ccbd05bfd67/nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl",
          "c6288de7d63e6cf62988f0923f96dc339cea362decb1bf5b3141883392a7d65e", 692992268),
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


def version_tag() -> str:
    """Folder name for the pinned set, e.g. 'cublas-12.9.2.10_cudnn-9.10.2.21'."""
    return "_".join(f"{w.name.split('-')[1]}-{w.version}" for w in WHEELS)


def installed(base: Optional[str] = None) -> bool:
    folder = os.path.join(base or runtime_dir(), version_tag())
    try:
        with open(os.path.join(folder, RUNTIME_MARKER), encoding="utf-8") as f:
            return json.load(f).get("wheels") == _expected()
    except (OSError, ValueError):
        return False


def cleanup(base: Optional[str] = None) -> None:
    """Remove runtime folders other than the pinned one, and leftovers of
    interrupted downloads. Call before CUDA is loaded."""
    base = base or runtime_dir()
    try:
        names = os.listdir(base)
    except OSError:
        return
    keep = version_tag()
    for name in names:
        if name != keep:
            path = os.path.join(base, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)


@dataclass
class Progress:
    # idle | downloading | extracting | activating | done | error | cancelled
    state: str = "idle"
    done_bytes: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        total = sum(w.size for w in WHEELS) or 1
        fraction = 1.0 if self.state in ("activating", "done") else \
            round(min(self.done_bytes / total, 1.0), 3)
        return {"state": self.state, "fraction": fraction, "message": self.message}


def _download(wheel: Wheel, path: str, progress: Progress, cancel: threading.Event, opener) -> None:
    digest = hashlib.sha256()
    try:
        with opener(wheel.url, timeout=30) as response, open(path, "wb") as out:
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


def _extract_dlls(wheel_path: str, dest: str, cancel: threading.Event) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        for member in zf.namelist():
            if cancel.is_set():
                raise SetupCancelled()
            parts = member.split("/")
            if len(parts) == 4 and parts[0] == "nvidia" and parts[2] == "bin" \
                    and parts[3].lower().endswith(".dll"):
                with zf.open(member) as src, open(os.path.join(dest, parts[3]), "wb") as dst:
                    shutil.copyfileobj(src, dst)


def install(progress: Progress, cancel: threading.Event, opener=urllib.request.urlopen,
            target: Optional[str] = None,
            check_driver: Optional[Callable[[], Optional[tuple[int, int]]]] = None) -> None:
    """Download, verify and unpack the pinned runtime into ``target``/<tag>.

    Never touches another version's folder (it may be loaded), and leaves
    nothing behind on failure or cancel.
    """
    base = target or runtime_dir()
    if installed(base):
        progress.state, progress.message = "done", "GPU acceleration is ready"
        return
    driver = (check_driver or driver_version)()
    if driver is not None and driver < MIN_DRIVER:
        raise SetupError(f"Update your NVIDIA driver first (you have {driver[0]}.{driver[1]:02d}; "
                         f"{MIN_DRIVER[0]}.{MIN_DRIVER[1]} or newer is needed).")
    dest = os.path.join(base, version_tag())
    staging = dest + ".partial"
    downloads = os.path.join(staging, "_downloads")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(downloads)
    try:
        for wheel in WHEELS:
            path = os.path.join(downloads, wheel.url.rsplit("/", 1)[-1])
            progress.state, progress.message = "downloading", f"Downloading {wheel.name}…"
            _download(wheel, path, progress, cancel, opener)
            progress.state, progress.message = "extracting", f"Unpacking {wheel.name}…"
            _extract_dlls(path, staging, cancel)
            os.remove(path)
        os.rmdir(downloads)
        with open(os.path.join(staging, RUNTIME_MARKER), "w", encoding="utf-8") as f:
            json.dump({"wheels": _expected()}, f)
        # An incomplete folder of this version was never loaded (it has no
        # marker), so it can be replaced.
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(staging, dest)
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

    def start(self, on_installed: Optional[Callable[[], None]] = None,
              on_done: Optional[Callable[[str], None]] = None) -> None:
        """``on_installed`` runs (in the background, before "done" is reported)
        once the runtime is in place -- e.g. to reload the model on the GPU."""
        if self.running:
            return
        self.progress = Progress(state="downloading", message="Starting…")
        self._cancel.clear()

        def _work():
            try:
                # Look urlopen up at call time (tests patch it).
                install(self.progress, self._cancel, opener=urllib.request.urlopen)
                if on_installed:
                    self.progress.state, self.progress.message = "activating", "Starting the GPU…"
                    on_installed()
                self.progress.state, self.progress.message = "done", "GPU acceleration is ready"
            except SetupCancelled:
                self.progress.state, self.progress.message = "cancelled", "Cancelled"
            except Exception as e:
                self.progress.state, self.progress.message = "error", str(e)
            if on_done:
                on_done(self.progress.state)

        self._thread = threading.Thread(target=_work, daemon=True, name="gpu-setup")
        self._thread.start()

    def cancel(self, wait: float = 0.0) -> None:
        """Cancel, optionally waiting up to ``wait`` s for the cleanup to finish."""
        self._cancel.set()
        if wait and self._thread:
            self._thread.join(wait)
