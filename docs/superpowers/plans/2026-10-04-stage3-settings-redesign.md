# Stage 3 — Settings redesign and packaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (run inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tabbed dark-glass settings window with a calm, native-feeling Windows 11 page:
- one scrolling page of cards;
- system light/dark theme and system accent colour;
- changes apply immediately, and errors appear on the card that caused them;
- a live mic level meter.

The stage ends with an installable build that bundles the GPU runtime.

**Architecture:**
- **Python side.** It exposes a few new bridge calls:
  - `get_system_info` (theme, accent, compute);
  - `get_status`;
  - a mic test: `start_mic_test`, `get_mic_level`, `stop_mic_test`.
  `save_config` reloads the model in the background so the UI never blocks.
- **React side.** It drops Tabs, ActionBar and the glass styles for Fluent CSS tokens.
  - A `useSettings` hook applies each change as it happens and polls status while the model loads.
- **GPU runtime.** `gpu_runtime.py` downloads the pinned NVIDIA wheels from PyPI and keeps only their DLLs. It is used in two places:
  - `ShuperWhisper.exe --setup-gpu`, a small progress window the installer runs when it finds an NVIDIA card;
  - a **Set up GPU acceleration** button in the new Processing section.
- **Packaging.**
  - A checked-in `packaging/build.py` drives PyInstaller in one-folder mode, producing `dist/ShuperWhisper` for the existing Inno Setup script. It no longer bundles any CUDA DLLs.
  - The installer detects an NVIDIA GPU over WMI and offers the download as a pre-ticked task.
  - The version is bumped to 2.0.0.

**Tech Stack:** pywebview 6, React 19, Tailwind 4 (tokens via CSS variables), Radix Select, lucide-react, PyInstaller, Inno Setup.

**Spec:** `docs/superpowers/specs/2026-10-04-live-dictation-design.md` (Stage 3 section)

**Depends on:** Stages 1 and 2 merged.

## Global Constraints

- Follow the system theme: `prefers-color-scheme` in the page, and a dark title bar via `DWMWA_USE_IMMERSIVE_DARK_MODE` when the system is dark.
- Font: `"Segoe UI Variable Text", "Segoe UI", sans-serif`. Base size 14px; card titles 14px/600; descriptions 12px muted.
- Light-mode colours:
  - page `#f3f3f3`, card `#fbfbfb`, card border `rgba(0,0,0,.06)`;
  - text `#1a1a1a`, muted `#5f5f5f`;
  - error `#c42b1c`;
  - accent: the system palette "Dark1", default `#0067c0`.
- Dark-mode colours:
  - page `#202020`, card `#2b2b2b`, card border `rgba(255,255,255,.06)`;
  - text `#ffffff`, muted `#c5c5c5`;
  - error `#ff99a4`;
  - accent: the system palette "Light2", default `#4cc2ff`.
- No Save/Cancel buttons. Every control applies on change.
- Every bridge call from React has a timeout (5 s, or 15 s for training).
- The GPU runtime is never bundled. It's downloaded only after the user opts in (installer task or Settings button), pinned by version and SHA-256.
- The app must work fully with no GPU runtime present.
- Tests: `python -m pytest tests/ -q` and `npm run build` before every commit.
- Conventional commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Branch: `feat/stage3-settings`. One PR on Gitea; never merge it.

---

### Task 0: Branch

- [ ] **Step 1**

```bash
cd D:/dev/hobby/projects/shuperwhisper && git checkout main && git pull && git checkout -b feat/stage3-settings
```

---

### Task 1: System theme, accent and window chrome (Python)

**Files:**
- Create: `shuper_whisper/system_theme.py`
- Test: `tests/test_system_theme.py`

**Interfaces:**
- Produces: `apps_use_dark() -> bool`
- Produces: `parse_accent_palette(raw: bytes) -> dict[str, str]`, returning `{"light": "#rrggbb", "dark": "#rrggbb"}`
- Produces: `accent_colors() -> dict[str, str]`
- Produces: `apply_window_theme(hwnd: int, dark: bool) -> None`
- Produces: `DEFAULT_ACCENTS = {"light": "#0067c0", "dark": "#4cc2ff"}`

- [ ] **Step 1: Write `tests/test_system_theme.py`**

```python
from shuper_whisper.system_theme import DEFAULT_ACCENTS, parse_accent_palette


def test_palette_picks_dark1_for_light_mode_and_light2_for_dark_mode():
    colours = [(0x99, 0xEB, 0xFF), (0x4C, 0xC2, 0xFF), (0x00, 0x91, 0xF8), (0x00, 0x78, 0xD4),
               (0x00, 0x67, 0xC0), (0x00, 0x3E, 0x92), (0x00, 0x1A, 0x68), (0xF7, 0x63, 0x0C)]
    raw = b"".join(bytes([r, g, b, 0]) for r, g, b in colours)
    assert parse_accent_palette(raw) == {"light": "#0067c0", "dark": "#4cc2ff"}


def test_bad_palette_falls_back():
    assert parse_accent_palette(b"\x00\x01") == DEFAULT_ACCENTS
```

Run: `python -m pytest tests/test_system_theme.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Create `shuper_whisper/system_theme.py`**

```python
"""Windows theme: light/dark, the user's accent colour, title-bar colour."""

import ctypes
import winreg

DEFAULT_ACCENTS = {"light": "#0067c0", "dark": "#4cc2ff"}
_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_ACCENT = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
DWMWA_USE_IMMERSIVE_DARK_MODE = 20


def _read(path: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def apps_use_dark() -> bool:
    return _read(_PERSONALIZE, "AppsUseLightTheme") == 0


def parse_accent_palette(raw) -> dict[str, str]:
    """AccentPalette is 8 RGBA swatches, lightest first: Light3, Light2,
    Light1, Base, Dark1, Dark2, Dark3, (unused). Windows uses Dark1 for
    accent fills in light mode and Light2 in dark mode."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 32:
        return dict(DEFAULT_ACCENTS)

    def swatch(i: int) -> str:
        r, g, b = raw[i * 4:i * 4 + 3]
        return f"#{r:02x}{g:02x}{b:02x}"
    return {"light": swatch(4), "dark": swatch(1)}


def accent_colors() -> dict[str, str]:
    return parse_accent_palette(_read(_ACCENT, "AccentPalette"))


def apply_window_theme(hwnd: int, dark: bool) -> None:
    """Dark or light title bar to match the page."""
    value = ctypes.c_int(1 if dark else 0)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except OSError:
        pass
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest tests/test_system_theme.py -q`
Expected: PASS. Then check against the real registry:

```bash
python -c "from shuper_whisper.system_theme import *; print(apps_use_dark(), accent_colors())"
```

- [ ] **Step 4: Commit**

```bash
git add shuper_whisper/system_theme.py tests/test_system_theme.py
git commit -m "feat(ui): read Windows light/dark mode and accent palette"
```

---

### Task 2: GPU runtime downloader

**Files:**
- Create: `shuper_whisper/gpu_runtime.py`
- Test: `tests/test_gpu_runtime.py`

**Interfaces:**
- Consumes: `transcriber.runtime_dir()` (stage 1)
- Produces:
  - `Wheel(name, version, url, sha256, size)` and the pinned `WHEELS`;
  - `MIN_DRIVER = (527, 41)`;
  - `driver_version() -> tuple[int, int] | None`;
  - `installed(target=None) -> bool`;
  - `Progress`, with `.to_dict() -> {"state", "fraction", "message"}`;
  - `install(progress, cancel, opener=urlopen, target=None, check_driver=None)` (None means `driver_version`), which raises `SetupError` or `SetupCancelled`;
  - `GpuSetup`, with `.start(on_done=None)`, `.cancel()`, `.running` and `.progress`.

- [ ] **Step 1: Write `tests/test_gpu_runtime.py`**

```python
"""GPU runtime downloader against a fake 'PyPI' serving tiny wheels."""

import hashlib
import io
import threading
import zipfile

import pytest

from shuper_whisper import gpu_runtime as gr


def make_wheel(lib: str, dlls: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in dlls.items():
            zf.writestr(f"nvidia/{lib}/bin/{name}", data)
        zf.writestr(f"nvidia/{lib}/include/{lib}.h", b"header")
        zf.writestr(f"nvidia_{lib}_cu12-1.0.dist-info/METADATA", b"meta")
    return buf.getvalue()


@pytest.fixture
def fake_pypi(monkeypatch):
    blobs = {
        "https://x/cublas.whl": make_wheel("cublas", {"cublas64_12.dll": b"A" * 3000}),
        "https://x/cudnn.whl": make_wheel("cudnn", {"cudnn64_9.dll": b"B" * 3000,
                                                    "cudnn_ops64_9.dll": b"C" * 10}),
    }
    monkeypatch.setattr(gr, "WHEELS", tuple(
        gr.Wheel(f"nvidia-{lib}-cu12", "1.0", url, hashlib.sha256(blob).hexdigest(), len(blob))
        for lib, (url, blob) in zip(("cublas", "cudnn"), blobs.items())))
    return lambda url, timeout=None: io.BytesIO(blobs[url])


def test_installs_only_dlls_and_marks_complete(fake_pypi, tmp_path):
    target = tmp_path / "cuda"
    progress = gr.Progress()
    gr.install(progress, threading.Event(), opener=fake_pypi, target=str(target),
               check_driver=lambda: (566, 36))
    assert sorted(p.name for p in target.iterdir()) == [
        "cublas64_12.dll", "cudnn64_9.dll", "cudnn_ops64_9.dll", "runtime.json"]
    assert gr.installed(str(target))
    assert progress.to_dict() == {"state": "done", "fraction": 1.0, "message": "GPU acceleration is ready"}


def test_corrupt_download_leaves_nothing(fake_pypi, tmp_path, monkeypatch):
    wheels = list(gr.WHEELS)
    wheels[1] = gr.Wheel(wheels[1].name, wheels[1].version, wheels[1].url, "0" * 64, wheels[1].size)
    monkeypatch.setattr(gr, "WHEELS", tuple(wheels))
    target = tmp_path / "cuda"
    with pytest.raises(gr.SetupError, match="corrupted"):
        gr.install(gr.Progress(), threading.Event(), opener=fake_pypi, target=str(target),
                   check_driver=lambda: None)
    assert not target.exists() and not (tmp_path / "cuda.partial").exists()


def test_cancel(fake_pypi, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(gr.SetupCancelled):
        gr.install(gr.Progress(), cancel, opener=fake_pypi, target=str(tmp_path / "cuda"),
                   check_driver=lambda: None)
    assert not (tmp_path / "cuda").exists()


def test_old_driver_refused_before_downloading(fake_pypi, tmp_path):
    opened = []
    with pytest.raises(gr.SetupError, match="Update your NVIDIA driver"):
        gr.install(gr.Progress(), threading.Event(),
                   opener=lambda *a, **k: opened.append(a), target=str(tmp_path / "cuda"),
                   check_driver=lambda: (472, 12))
    assert opened == []


def test_installed_requires_matching_versions(fake_pypi, tmp_path):
    target = tmp_path / "cuda"
    target.mkdir()
    (target / "runtime.json").write_text('{"wheels": {"nvidia-cublas-cu12": "0.9"}}')
    assert not gr.installed(str(target))


def test_gpu_setup_runs_in_background(fake_pypi, tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "runtime_dir", lambda: str(tmp_path / "cuda"))
    monkeypatch.setattr(gr, "driver_version", lambda: None)
    monkeypatch.setattr(gr.urllib.request, "urlopen", fake_pypi)
    finished = threading.Event()
    states = []
    setup = gr.GpuSetup()
    setup.start(on_done=lambda state: (states.append(state), finished.set()))
    assert finished.wait(5)
    assert states == ["done"] and not setup.running
```

Run: `python -m pytest tests/test_gpu_runtime.py -q`.
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Create `shuper_whisper/gpu_runtime.py`**

```python
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
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest tests/test_gpu_runtime.py -q`
Expected: PASS.

- [ ] **Step 4: Real download (≈1.3 GB, ~2–10 min)**

```bash
python -c "
import threading, time; from shuper_whisper import gpu_runtime as g
s=g.GpuSetup(); s.start(on_done=print)
while s.running: print(s.progress.to_dict()); time.sleep(5)"
python -c "from shuper_whisper.transcriber import select_compute, runtime_dir; print(runtime_dir(), select_compute())"
```

Expected:
- progress climbs to `done`;
- `%LOCALAPPDATA%\ShuperWhisper\cuda` holds `cublas64_12.dll`, `cudnn64_9.dll`, … and `runtime.json`;
- `select_compute()` returns `('cuda', 'float16')` even after `pip uninstall nvidia-cublas-cu12 nvidia-cudnn-cu12`.

Reinstall the extra afterwards with `pip install -e .[gpu]`.

- [ ] **Step 5: Commit**

```bash
git add shuper_whisper/gpu_runtime.py tests/test_gpu_runtime.py
git commit -m "feat(gpu): on-demand download of the pinned CUDA runtime with hash checks"
```

---

### Task 3: `--setup-gpu` progress window

**Files:**
- Create: `shuper_whisper/setup_window.py`
- Modify: `shuper_whisper/app.py` (`main`)
- Test: `tests/test_app_main.py`

**Interfaces:**
- Consumes: `gpu_runtime.GpuSetup`
- Produces: `run_setup_window() -> int`, which returns 0 when the runtime ended up installed and 1 otherwise. `main()` exits with that code for `--setup-gpu`.

- [ ] **Step 1: Test the entry point**

Append to `tests/test_app_main.py`:

```python
def test_setup_gpu_flag_runs_setup_window_and_exits(mocker, stub_main):
    run = mocker.patch("shuper_whisper.setup_window.run_setup_window", return_value=0)
    tray = mocker.patch("shuper_whisper.tray.TrayController")
    mocker.patch.object(sys, "argv", ["shuper-whisper", "--setup-gpu"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 0
    run.assert_called_once()
    tray.assert_not_called()
    assert "config" not in stub_main
```

Run: `python -m pytest tests/test_app_main.py -q`
Expected: FAIL (the flag is ignored and the tray starts).

- [ ] **Step 2: Create `shuper_whisper/setup_window.py`**

```python
"""Small window for `ShuperWhisper.exe --setup-gpu` (run by the installer)."""

import webview

from . import gpu_runtime

_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  :root { --bg:#f3f3f3; --fg:#1a1a1a; --muted:#5f5f5f; --accent:#0067c0; --track:rgba(0,0,0,.1); --error:#c42b1c; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#202020; --fg:#fff; --muted:#c5c5c5; --accent:#4cc2ff; --track:rgba(255,255,255,.12); --error:#ff99a4; } }
  body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
         font:14px/20px "Segoe UI Variable Text","Segoe UI",sans-serif; user-select:none; }
  h1 { font-size:20px; line-height:28px; font-weight:600; margin:0 0 4px; }
  p { margin:0 0 16px; color:var(--muted); font-size:13px; }
  .track { height:4px; border-radius:2px; background:var(--track); overflow:hidden; }
  .bar { height:100%; width:0; background:var(--accent); transition:width .2s; }
  .row { display:flex; justify-content:space-between; align-items:center; margin-top:16px; }
  #msg { font-size:12px; color:var(--muted); } #msg.error { color:var(--error); }
  button { font:inherit; padding:5px 16px; border-radius:4px; border:1px solid var(--track);
           background:transparent; color:var(--fg); }
</style></head><body>
  <h1>Setting up GPU acceleration</h1>
  <p>Downloading NVIDIA's libraries (about 1.3 GB) so ShuperWhisper can type live as you speak.</p>
  <div class="track"><div class="bar" id="bar"></div></div>
  <div class="row"><span id="msg">Starting…</span><button id="btn" onclick="act()">Cancel</button></div>
<script>
  var finished = false;
  function act() { finished ? pywebview.api.close() : pywebview.api.cancel(); }
  function tick() {
    pywebview.api.progress().then(function (p) {
      document.getElementById('bar').style.width = (p.fraction * 100) + '%';
      var msg = document.getElementById('msg');
      msg.textContent = p.message + (p.state === 'downloading' ? ' ' + Math.round(p.fraction * 100) + '%' : '');
      msg.className = p.state === 'error' ? 'error' : '';
      if (['done', 'error', 'cancelled'].indexOf(p.state) >= 0) {
        finished = true;
        document.getElementById('btn').textContent = 'Close';
        if (p.state === 'done') setTimeout(function () { pywebview.api.close(); }, 1500);
      } else { setTimeout(tick, 250); }
    });
  }
  window.addEventListener('pywebviewready', function () { pywebview.api.start(); tick(); });
</script></body></html>"""


class _Api:
    def __init__(self, setup: gpu_runtime.GpuSetup):
        self._setup = setup
        self.window = None

    def start(self):
        if gpu_runtime.installed():
            self._setup.progress = gpu_runtime.Progress(state="done", message="Already set up")
            return
        self._setup.start()

    def progress(self):
        return self._setup.progress.to_dict()

    def cancel(self):
        self._setup.cancel()

    def close(self):
        if self.window:
            self.window.destroy()


def run_setup_window() -> int:
    setup = gpu_runtime.GpuSetup()
    api = _Api(setup)
    api.window = webview.create_window("Set up GPU acceleration", html=_HTML, js_api=api,
                                       width=480, height=230, resizable=False)
    webview.start()
    setup.cancel()  # window closed mid-download
    return 0 if gpu_runtime.installed() else 1
```

- [ ] **Step 3: Hook it into `main()` in `app.py`**

Right after `_enable_dpi_awareness()`, add:

```python
    if "--setup-gpu" in sys.argv:
        from .setup_window import run_setup_window
        sys.exit(run_setup_window())
```

- [ ] **Step 4: Run the tests and try it**

Run `python -m pytest tests/test_app_main.py -q`. Expected: PASS.

Then run `python main.py --setup-gpu`. Expected:
- if Task 2 Step 4 already downloaded the runtime, the window shows "Already set up" and closes;
- otherwise you see the progress bar, and Cancel works.

- [ ] **Step 5: Commit**

```bash
git add shuper_whisper/setup_window.py shuper_whisper/app.py tests/test_app_main.py
git commit -m "feat(gpu): --setup-gpu progress window for the installer"
```

---

### Task 4: Bridge — status, system info, mic test, background model reload

**Files:**
- Modify: `shuper_whisper/bridge.py`, `shuper_whisper/transcriber.py`
- Test: `tests/test_bridge_settings.py`

**Interfaces:**
- Consumes: `system_theme`, `AudioRecorder`, `app.error`, and `app.transcriber.device` / `.model_size`.
- Produces: `transcriber.gpu_name() -> str | None`
- Produces these `WindowAPI` methods:
  - `get_system_info() -> {"dark": bool, "accent": {"light", "dark"}, "compute": str}`
  - `get_status() -> {"state": str, "error": str | None}`
  - `start_mic_test(device_ref) -> {"success": bool, "error"?: str}`
  - `get_mic_level() -> float`
  - `stop_mic_test() -> None`
- Changes `save_config(data)`: it returns `{"success": True, "loading": True, "config": ...}` when the model changes, and the reload runs on a background thread.
- Requires `ShuperWhisperApp` to expose `state` (the last state passed to `_set_state`).
- Produces these GPU calls:
  - `get_gpu_status() -> {"gpu": str | None, "installed": bool, "active": bool}`
  - `setup_gpu() -> {"success": True}`
  - `get_gpu_setup_progress() -> {"state", "fraction", "message"}`
  - `cancel_gpu_setup() -> None`

  When setup succeeds, the app reloads its model so the GPU is picked up without a restart.
- Changes `ShuperWhisperApp.reload_config(new_config, force_model=False)`. `force_model=True` reloads the model even when settings are unchanged.

- [ ] **Step 1: Track the current state in the app, and allow a forced model reload**

In `shuper_whisper/app.py`:
- add `self.state = STATE_IDLE` to `ShuperWhisperApp.__init__`;
- add `self.state = state` as the first line of `_set_state`;
- change the signature to `def reload_config(self, new_config: AppConfig, force_model: bool = False) -> None:`;
- change `if model_changed or not self.transcriber.loaded:` to `if force_model or model_changed or not self.transcriber.loaded:`.

Add to `tests/test_app_lifecycle.py`:

```python
def test_force_model_reload(make_app):
    a = make_app()
    a.start()
    t = a.transcriber
    a.reload_config(a.config, force_model=True)
    assert a.transcriber is not t
```

- [ ] **Step 2: Write `tests/test_bridge_settings.py`**

```python
"""Bridge calls used by the redesigned settings page."""

import threading
from unittest.mock import MagicMock

import pytest

from shuper_whisper import bridge as bridge_mod
from shuper_whisper.bridge import WindowAPI
from shuper_whisper.config import AppConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    app = MagicMock()
    app.state, app.error = "idle", None
    app.transcriber.device = "cuda"
    app.transcriber.model_size = "large-v3-turbo"
    app.config = AppConfig()
    a = WindowAPI()
    a.set_app_instance(app)
    monkeypatch.setattr("shuper_whisper.config._default_config_path",
                        lambda: str(tmp_path / "config.json"))
    return a


def test_status(api):
    api._app.state, api._app.error = "error", "Mic gone"
    assert api.get_status() == {"state": "error", "error": "Mic gone"}


def test_system_info(api, monkeypatch):
    monkeypatch.setattr(bridge_mod.system_theme, "apps_use_dark", lambda: True)
    monkeypatch.setattr(bridge_mod.system_theme, "accent_colors",
                        lambda: {"light": "#0067c0", "dark": "#4cc2ff"})
    monkeypatch.setattr(bridge_mod, "gpu_name", lambda: "NVIDIA GeForce RTX 3080")
    info = api.get_system_info()
    assert info["dark"] is True
    assert info["compute"] == "Large v3 Turbo on NVIDIA GeForce RTX 3080"


def test_cpu_compute_label(api, monkeypatch):
    api._app.transcriber.device = "cpu"
    api._app.transcriber.model_size = "base"
    monkeypatch.setattr(bridge_mod, "gpu_name", lambda: None)
    assert api.get_system_info()["compute"] == "Base on CPU"


def test_model_change_reloads_in_background(api):
    started = threading.Event()
    api._app.reload_config.side_effect = lambda c: started.set()
    result = api.save_config({"model_size": "small"})
    assert result["success"] and result["loading"]
    assert started.wait(2)


def test_hotkey_change_applies_synchronously(api):
    result = api.save_config({"hotkey": "f9"})
    assert result["success"] and not result.get("loading")
    api._app.reload_config.assert_called_once()


class FakeRecorder:
    def __init__(self, device_ref=None):
        self.device_ref = device_ref
        self.stopped = False

    def start_recording(self):
        if self.device_ref == {"name": "Broken", "hostapi": None}:
            raise RuntimeError("Invalid sample rate")

    def get_levels(self, n):
        return [0.0] * (n - 1) + [0.2]

    def stop_recording(self):
        self.stopped = True


def test_mic_test_round_trip(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "AudioRecorder", FakeRecorder)
    assert api.start_mic_test({"name": "B1", "hostapi": None}) == {"success": True}
    assert api.get_mic_level() == pytest.approx(0.2)
    recorder = api._mic_test
    api.stop_mic_test()
    assert recorder.stopped and api._mic_test is None


def test_gpu_status(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "gpu_name", lambda: "NVIDIA GeForce RTX 3080")
    monkeypatch.setattr(bridge_mod.gpu_runtime, "installed", lambda: False)
    assert api.get_gpu_status() == {"gpu": "NVIDIA GeForce RTX 3080", "installed": False, "active": True}


def test_gpu_setup_success_reloads_model(api, monkeypatch):
    class FakeSetup:
        progress = bridge_mod.gpu_runtime.Progress(state="done", message="ok")

        def start(self, on_done=None):
            on_done("done")
    monkeypatch.setattr(bridge_mod, "_gpu_setup", FakeSetup())
    assert api.setup_gpu() == {"success": True}
    api._app.reload_config.assert_called_once_with(api._app.config, force_model=True)
    assert api.get_gpu_setup_progress()["state"] == "done"


def test_mic_test_error(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "AudioRecorder", FakeRecorder)
    result = api.start_mic_test({"name": "Broken", "hostapi": None})
    assert result == {"success": False, "error": "Invalid sample rate"}
    assert api.get_mic_level() == 0.0
```

Run: `python -m pytest tests/test_bridge_settings.py -q`
Expected: FAIL (the new methods don't exist).

- [ ] **Step 3: Add `gpu_name` to `transcriber.py`**

Add `import functools` to the file. The result is cached because `nvidia-smi` takes about 100 ms and the page asks for it more than once.

```python
@functools.lru_cache(maxsize=1)
def gpu_name() -> Optional[str]:
    """Name of the first NVIDIA GPU, via nvidia-smi (None if unavailable)."""
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW)
        name = out.stdout.strip().splitlines()[0].strip()
        return name or None
    except Exception:
        return None
```

- [ ] **Step 4: Extend `shuper_whisper/bridge.py`**

At the top, add:

```python
from . import gpu_runtime, system_theme
from .audio import AudioRecorder
from .transcriber import gpu_name

# One download at a time, shared by every settings window.
_gpu_setup = gpu_runtime.GpuSetup()

_MODEL_LABELS = {"large-v3-turbo": "Large v3 Turbo", "large-v3": "Large v3"}
```

In `WindowAPI.__init__`, add `self._mic_test = None`.

Replace `save_config` with:

```python
    def save_config(self, data):
        """Validate, check the mic, save and apply.

        Model changes reload in the background (seconds); the page polls
        get_status() until the state leaves "loading".
        """
        from . import audio_devices
        from .config import AppConfig, load_config, save_config

        try:
            current = load_config()
            merged = {**current.to_dict(), **(data or {})}
            config = AppConfig(
                hotkey=merged.get('hotkey', 'ctrl+shift+space'),
                model_size=merged.get('model_size', 'auto'),
                input_device=merged.get('input_device'),
                language=merged.get('language', 'en'),
            )
            config.validate()
            if config.input_device != current.input_device:
                problem = audio_devices.check(config.input_device)
                if problem:
                    return {'success': False, 'error': f"Can't use that microphone: {problem}"}
            save_config(config)
            if not self._app:
                return {'success': True, 'config': config.to_dict()}
            if config.model_size != current.model_size:
                threading.Thread(target=self._app.reload_config, args=(config,), daemon=True).start()
                return {'success': True, 'loading': True, 'config': config.to_dict()}
            self._app.reload_config(config)
            if self._app.error:
                return {'success': False, 'error': self._app.error}
            return {'success': True, 'config': config.to_dict()}
        except Exception as e:
            return {'success': False, 'error': str(e)}
```

Add the new calls:

```python
    # ------------------------------------------------------------------
    # Status and system info
    # ------------------------------------------------------------------

    def get_status(self):
        if not self._app:
            return {'state': 'idle', 'error': None}
        return {'state': self._app.state, 'error': self._app.error}

    def get_system_info(self):
        compute = "Not loaded"
        if self._app and self._app.transcriber.device:
            size = self._app.transcriber.model_size
            label = _MODEL_LABELS.get(size, size.capitalize())
            where = (gpu_name() or "NVIDIA GPU") if self._app.transcriber.device == "cuda" else "CPU"
            compute = f"{label} on {where}"
        return {
            'dark': system_theme.apps_use_dark(),
            'accent': system_theme.accent_colors(),
            'compute': compute,
        }

    # ------------------------------------------------------------------
    # Mic test (level meter on the Microphone card)
    # ------------------------------------------------------------------

    def start_mic_test(self, device_ref):
        self.stop_mic_test()
        recorder = AudioRecorder(device_ref=device_ref)
        try:
            recorder.start_recording()
        except Exception as e:
            return {'success': False, 'error': str(e)}
        self._mic_test = recorder
        return {'success': True}

    def get_mic_level(self):
        if not self._mic_test:
            return 0.0
        return float(self._mic_test.get_levels(1)[-1])

    def stop_mic_test(self):
        recorder, self._mic_test = self._mic_test, None
        if recorder:
            try:
                recorder.stop_recording()
            except Exception:
                pass
```

Make sure `close_window` calls `self.stop_mic_test()` before destroying the window.

Add the GPU calls:

```python
    # ------------------------------------------------------------------
    # GPU acceleration
    # ------------------------------------------------------------------

    def get_gpu_status(self):
        return {
            'gpu': gpu_name(),
            'installed': gpu_runtime.installed(),
            'active': bool(self._app and self._app.transcriber.device == 'cuda'),
        }

    def setup_gpu(self):
        def _done(state):
            if state == 'done' and self._app:
                self._app.reload_config(self._app.config, force_model=True)
        _gpu_setup.start(on_done=_done)
        return {'success': True}

    def get_gpu_setup_progress(self):
        return _gpu_setup.progress.to_dict()

    def cancel_gpu_setup(self):
        _gpu_setup.cancel()
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shuper_whisper/bridge.py shuper_whisper/transcriber.py shuper_whisper/app.py tests/test_bridge_settings.py tests/test_app_lifecycle.py
git commit -m "feat(bridge): system info, status polling, mic test, GPU setup, background model reload"
```

---

### Task 5: Settings window chrome

**Files:**
- Modify: `shuper_whisper/tray.py`

- [ ] **Step 1: Replace `_open_settings` in `tray.py`**

```python
    def _open_settings(self, icon, item) -> None:
        """Open (or focus) the settings window."""
        dist_index = os.path.join(_DIST_DIR, 'index.html')
        if not os.path.exists(dist_index):
            print(f"WARNING: React build not found at {dist_index}")
            return
        existing = [w for w in webview.windows if w.title == 'ShuperWhisper Settings']
        if existing:
            existing[0].restore()
            existing[0].show()
            return

        port = _ensure_static_server()
        api = WindowAPI()
        api.set_app_instance(self.app)
        dark = system_theme.apps_use_dark()
        window = webview.create_window(
            'ShuperWhisper Settings',
            url=f'http://127.0.0.1:{port}/',
            width=560,
            height=700,
            min_size=(460, 520),
            resizable=True,
            background_color='#202020' if dark else '#f3f3f3',
            js_api=api,
        )
        api._window = window

        def _style():
            hwnd = ctypes.windll.user32.FindWindowW(None, 'ShuperWhisper Settings')
            if hwnd:
                system_theme.apply_window_theme(hwnd, dark)
        window.events.shown += _style
        window.events.closed += api.stop_mic_test
```

Add `import ctypes` and `from . import system_theme` to the imports.

- [ ] **Step 2: Commit**

```bash
git add shuper_whisper/tray.py
git commit -m "feat(ui): resizable settings window that follows the system theme"
```

---

### Task 6: Fluent styles and primitives

**Files:**
- Modify: `shuper_whisper/ui/src/index.css` (rewrite), `ui/index.html`, `ui/package.json`
- Create: `ui/src/components/fluent.tsx`
- Delete: `ui/src/components/StyledSelect.tsx`, `ActionBar.tsx`, `TabNav.tsx`, `GeneralTab.tsx`

**Interfaces:**
- Produces in `fluent.tsx`:
  - `Section({title, children})`
  - `Card({icon, title, description?, error?, children?, below?})`
  - `Select({value, onChange, options, disabled?})`
  - `Toggle({checked, onChange, label})`
  - `Button({onClick, children, variant?: "accent" | "standard", disabled?})`
  - `LevelMeter({level})`

- [ ] **Step 1: Rewrite `ui/src/index.css`**

```css
@import "tailwindcss";

/*
 * Fluent tokens. Light by default, dark via prefers-color-scheme (WebView2
 * follows the Windows app theme). --accent is overwritten from Python with
 * the user's system accent colour.
 * Custom CSS lives in @layer blocks so Tailwind utilities still win.
 */
@layer base {
  :root {
    --page: #f3f3f3;
    --card: #fbfbfb;
    --card-hover: #f6f6f6;
    --stroke: rgba(0, 0, 0, 0.06);
    --control: rgba(255, 255, 255, 0.7);
    --control-hover: rgba(249, 249, 249, 0.5);
    --control-stroke: rgba(0, 0, 0, 0.0578);
    --control-stroke-bottom: rgba(0, 0, 0, 0.1622);
    --text: #1a1a1a;
    --muted: #5f5f5f;
    --error: #c42b1c;
    --accent: #0067c0;
    --on-accent: #ffffff;
    --flyout: #f9f9f9;
    color-scheme: light;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --page: #202020;
      --card: #2b2b2b;
      --card-hover: #323232;
      --stroke: rgba(255, 255, 255, 0.06);
      --control: rgba(255, 255, 255, 0.061);
      --control-hover: rgba(255, 255, 255, 0.084);
      --control-stroke: rgba(255, 255, 255, 0.07);
      --control-stroke-bottom: rgba(255, 255, 255, 0.05);
      --text: #ffffff;
      --muted: #c5c5c5;
      --error: #ff99a4;
      --accent: #4cc2ff;
      --on-accent: #000000;
      --flyout: #2c2c2c;
      color-scheme: dark;
    }
  }

  html, body, #root {
    height: 100%;
    margin: 0;
    background: var(--page);
    color: var(--text);
    font: 14px/20px "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }

  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-thumb { background: color-mix(in srgb, var(--text) 25%, transparent); border-radius: 4px; border: 2px solid var(--page); }
  ::-webkit-scrollbar-track { background: transparent; }

  :focus-visible { outline: 2px solid var(--text); outline-offset: 1px; border-radius: 4px; }
}

@layer components {
  .card {
    background: var(--card);
    border: 1px solid var(--stroke);
    border-radius: 6px;
  }

  .control {
    background: var(--control);
    border: 1px solid var(--control-stroke);
    border-bottom-color: var(--control-stroke-bottom);
    border-radius: 4px;
    color: var(--text);
    transition: background 0.08s ease;
  }
  .control:hover:not(:disabled) { background: var(--control-hover); }
  .control:disabled { opacity: 0.5; }

  .btn-accent {
    background: var(--accent);
    color: var(--on-accent);
    border: 1px solid transparent;
    border-radius: 4px;
  }
  .btn-accent:hover:not(:disabled) { filter: brightness(1.08); }
  .btn-accent:disabled { opacity: 0.4; }

  .text-muted { color: var(--muted); }
  .text-error { color: var(--error); }
  .text-accent { color: var(--accent); }
}

[data-radix-popper-content-wrapper] { z-index: 50 !important; }
```

- [ ] **Step 2: Update `ui/index.html`**

- Remove `class="dark"` from `<html>`.
- Change the boot div's inline style to `style="padding:20px;font:13px 'Segoe UI';opacity:.6"`.
- Change the error handler's colour from `#ff4466` to `#c42b1c`.

- [ ] **Step 3: Create `ui/src/components/fluent.tsx`**

```tsx
import * as RSelect from "@radix-ui/react-select";
import { Check, ChevronDown, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h2 className="text-[14px] font-semibold mt-5 mb-1.5">{title}</h2>
      {children}
    </section>
  );
}

export function Card({
  icon: Icon, title, description, error, children, below,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  error?: string | null;
  children?: ReactNode;
  below?: ReactNode;
}) {
  return (
    <div className="card">
      <div className="flex items-center gap-4 px-4 py-3 min-h-[68px]">
        <Icon size={20} strokeWidth={1.5} className="shrink-0 opacity-90" />
        <div className="flex-1 min-w-0">
          <div className="text-[14px]">{title}</div>
          {description && <div className="text-[12px] text-muted leading-4 mt-0.5">{description}</div>}
          {error && <div className="text-[12px] text-error leading-4 mt-1">{error}</div>}
        </div>
        {children && <div className="shrink-0 max-w-[60%]">{children}</div>}
      </div>
      {below && <div className="border-t border-[var(--stroke)] px-4 py-3">{below}</div>}
    </div>
  );
}

export function Select({
  value, onChange, options, disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
}) {
  const label = options.find((o) => o.value === value)?.label ?? value;
  return (
    <RSelect.Root value={value} onValueChange={onChange} disabled={disabled}>
      <RSelect.Trigger className="control h-8 min-w-[200px] max-w-[280px] px-3 flex items-center justify-between gap-2 text-[14px] outline-none">
        <span className="truncate"><RSelect.Value>{label}</RSelect.Value></span>
        <RSelect.Icon><ChevronDown size={14} className="text-muted" /></RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={4}
          className="rounded-lg border border-[var(--stroke)] bg-[var(--flyout)] shadow-[0_8px_16px_rgba(0,0,0,0.14)] overflow-hidden"
        >
          <RSelect.Viewport className="p-1 max-h-[300px]">
            {options.map((o) => (
              <RSelect.Item
                key={o.value}
                value={o.value}
                className="relative flex items-center gap-2 h-8 pl-7 pr-3 rounded text-[14px] cursor-default outline-none data-[highlighted]:bg-[var(--control-hover)]"
              >
                <RSelect.ItemIndicator className="absolute left-2 text-accent"><Check size={14} /></RSelect.ItemIndicator>
                <RSelect.ItemText>{o.label}</RSelect.ItemText>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

export function Toggle({
  checked, onChange, label,
}: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-3 text-[14px]"
    >
      <span className="text-muted">{checked ? "On" : "Off"}</span>
      <span
        className={cn(
          "relative w-10 h-5 rounded-full border transition-colors",
          checked ? "bg-[var(--accent)] border-transparent" : "border-[var(--muted)]"
        )}
      >
        <span
          className={cn(
            "absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all",
            checked ? "left-[22px] bg-[var(--on-accent)]" : "left-[3px] bg-[var(--muted)]"
          )}
        />
      </span>
    </button>
  );
}

export function Button({
  onClick, children, variant = "standard", disabled,
}: { onClick: () => void; children: ReactNode; variant?: "accent" | "standard"; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn("h-8 px-3 text-[14px] inline-flex items-center gap-2", variant === "accent" ? "btn-accent" : "control")}
    >
      {children}
    </button>
  );
}

export function LevelMeter({ level }: { level: number }) {
  const pct = Math.min(100, Math.round((level / 0.15) * 100));
  return (
    <div className="h-1 w-full rounded-full bg-[var(--control-stroke-bottom)] overflow-hidden" aria-label="Microphone level">
      <div className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-75" style={{ width: `${pct}%` }} />
    </div>
  );
}
```

- [ ] **Step 4: Remove the old components and unused packages**

```bash
git rm shuper_whisper/ui/src/components/StyledSelect.tsx shuper_whisper/ui/src/components/ActionBar.tsx shuper_whisper/ui/src/components/TabNav.tsx shuper_whisper/ui/src/components/GeneralTab.tsx
cd shuper_whisper/ui && npm uninstall @radix-ui/react-slider @radix-ui/react-switch @radix-ui/react-tabs class-variance-authority
```

The build is broken until Task 8 rewrites `App.tsx`, so don't commit yet. Continue straight into Task 7.

---

### Task 7: Settings data hook

**Files:**
- Modify: `ui/src/lib/bridge.ts`, `ui/src/lib/types.ts`
- Create: `ui/src/hooks/useSettings.ts`
- Delete: `ui/src/hooks/useConfig.ts`

**Interfaces:**
- Produces in `types.ts`: `SystemInfo { dark: boolean; accent: { light: string; dark: string }; compute: string }` and `AppStatus { state: string; error: string | null }`.
- Produces in `bridge.ts`:
  - `withTimeout<T>(p: Promise<T>, ms?: number): Promise<T>`
  - `getSystemInfo()`, `getStatus()`
  - `startMicTest(ref)`, `getMicLevel()`, `stopMicTest()`
  - `getAutostart()`, `setAutostart(on)`
- Produces: `useSettings()`, which returns `{config, options, devices, system, status, loading, loadError, errors, apply, refreshSystem}`.
  - `errors` is `Partial<Record<keyof AppConfig, string>>`.
  - `apply(patch: Partial<AppConfig>) => Promise<void>`.

- [ ] **Step 1: Extend `types.ts`**

```ts
export interface SystemInfo {
  dark: boolean;
  accent: { light: string; dark: string };
  compute: string;
}

export interface AppStatus {
  state: "idle" | "recording" | "processing" | "loading" | "error";
  error: string | null;
}

export interface GpuStatus {
  gpu: string | null;
  installed: boolean;
  active: boolean;
}

export interface GpuSetupProgress {
  state: "idle" | "downloading" | "extracting" | "done" | "error" | "cancelled";
  fraction: number;
  message: string;
}
```

- [ ] **Step 2: Extend `bridge.ts`**

Add these members to `PyWebViewAPI`:

```ts
  get_status: () => Promise<AppStatus>;
  get_system_info: () => Promise<SystemInfo>;
  start_mic_test: (ref: DeviceRef | null) => Promise<{ success: boolean; error?: string }>;
  get_mic_level: () => Promise<number>;
  stop_mic_test: () => Promise<void>;
  get_autostart: () => Promise<boolean>;
  set_autostart: (enabled: boolean) => Promise<boolean>;
  get_gpu_status: () => Promise<GpuStatus>;
  setup_gpu: () => Promise<{ success: boolean }>;
  get_gpu_setup_progress: () => Promise<GpuSetupProgress>;
  cancel_gpu_setup: () => Promise<void>;
```

In `save_config`'s return type, add `loading?: boolean`, and change the `saveConfig` wrapper's return type to match. Import `AppStatus`, `SystemInfo`, `DeviceRef`, `GpuStatus` and `GpuSetupProgress` from `./types`.

Append:

```ts
export function withTimeout<T>(p: Promise<T>, ms = 5000): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("ShuperWhisper didn't respond")), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

function api(): PyWebViewAPI {
  const a = getApi();
  if (!a) throw new Error("Bridge not available");
  return a;
}

export const getStatus = () => withTimeout(api().get_status());
export const getSystemInfo = () => withTimeout(api().get_system_info());
export const startMicTest = (ref: DeviceRef | null) => withTimeout(api().start_mic_test(ref));
export const getMicLevel = () => withTimeout(api().get_mic_level(), 1000);
export const stopMicTest = () => withTimeout(api().stop_mic_test());
export const getAutostart = () => withTimeout(api().get_autostart());
export const setAutostart = (on: boolean) => withTimeout(api().set_autostart(on));
export const getGpuStatus = () => withTimeout(api().get_gpu_status(), 8000);
export const setupGpu = () => withTimeout(api().setup_gpu());
export const getGpuSetupProgress = () => withTimeout(api().get_gpu_setup_progress(), 2000);
export const cancelGpuSetup = () => withTimeout(api().cancel_gpu_setup());
```

In `trainWord`, wrap the call: `return withTimeout(api.train_word(word), 15000);`.

- [ ] **Step 3: Create `ui/src/hooks/useSettings.ts`**

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import type { AppConfig, AppStatus, ConfigOptions, Device, SystemInfo } from "@/lib/types";
import {
  getConfig, getConfigOptions, getDevices, getStatus, getSystemInfo,
  saveConfig, waitForBridge, withTimeout,
} from "@/lib/bridge";

type FieldErrors = Partial<Record<keyof AppConfig, string>>;

/** Load settings once; apply each change immediately; poll status while the model loads. */
export function useSettings() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [options, setOptions] = useState<ConfigOptions | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [status, setStatus] = useState<AppStatus>({ state: "idle", error: null });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const polling = useRef<number | null>(null);

  const refreshSystem = useCallback(async () => {
    try {
      const info = await getSystemInfo();
      setSystem(info);
      const root = document.documentElement.style;
      root.setProperty("--accent", info.dark ? info.accent.dark : info.accent.light);
    } catch { /* keep defaults */ }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await waitForBridge();
        const [cfg, opts, devs, st] = await Promise.all([
          withTimeout(getConfig()), withTimeout(getConfigOptions()),
          withTimeout(getDevices(), 8000), getStatus(),
        ]);
        setConfig(cfg); setOptions(opts); setDevices(devs); setStatus(st);
        await refreshSystem();
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Couldn't load settings");
      } finally {
        setLoading(false);
      }
    })();
    return () => { if (polling.current) clearInterval(polling.current); };
  }, [refreshSystem]);

  const pollUntilSettled = useCallback(() => {
    if (polling.current) clearInterval(polling.current);
    polling.current = window.setInterval(async () => {
      try {
        const st = await getStatus();
        setStatus(st);
        if (st.state !== "loading") {
          clearInterval(polling.current!);
          polling.current = null;
          await refreshSystem();
        }
      } catch { /* keep polling */ }
    }, 500);
  }, [refreshSystem]);

  const apply = useCallback(async (patch: Partial<AppConfig>) => {
    if (!config) return;
    const previous = config;
    const keys = Object.keys(patch) as (keyof AppConfig)[];
    setConfig({ ...config, ...patch });
    setErrors((e) => { const n = { ...e }; keys.forEach((k) => delete n[k]); return n; });
    try {
      const result = await withTimeout(saveConfig({ ...config, ...patch }), 10000);
      if (!result.success) {
        setConfig(previous);
        setErrors((e) => ({ ...e, [keys[0]]: result.error ?? "Couldn't apply that" }));
        return;
      }
      if (result.loading) {
        setStatus({ state: "loading", error: null });
        pollUntilSettled();
      } else {
        setStatus(await getStatus());
      }
    } catch (e) {
      setConfig(previous);
      setErrors((er) => ({ ...er, [keys[0]]: e instanceof Error ? e.message : "Couldn't apply that" }));
    }
  }, [config, pollUntilSettled]);

  return { config, options, devices, system, status, loading, loadError, errors, apply, refreshSystem };
}
```

```bash
git rm shuper_whisper/ui/src/hooks/useConfig.ts
```

Continue into Task 8; there is no commit yet.

---

### Task 8: The settings page

**Files:**
- Modify: `ui/src/App.tsx` (rewrite)
- Create: `ui/src/components/MicrophoneCard.tsx`, `ui/src/components/ShortcutCard.tsx`
- Rename and restyle: `ui/src/components/DictionaryTab.tsx` → `ui/src/components/DictionarySection.tsx`

- [ ] **Step 1: `ShortcutCard.tsx`**

```tsx
import { useState } from "react";
import { Keyboard } from "lucide-react";
import { captureHotkey } from "@/lib/bridge";
import { Button, Card } from "./fluent";

const pretty = (hotkey: string) =>
  hotkey.split("+").map((k) => (k.length === 1 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1))).join(" + ");

export function ShortcutCard({
  hotkey, error, onChange,
}: { hotkey: string; error?: string; onChange: (h: string) => void }) {
  const [capturing, setCapturing] = useState(false);
  const capture = async () => {
    setCapturing(true);
    try {
      const key = await captureHotkey();
      if (key) onChange(key);
    } finally {
      setCapturing(false);
    }
  };
  return (
    <Card icon={Keyboard} title="Dictation shortcut"
          description="Press once to start dictating, press again to stop." error={error}>
      <Button onClick={capture}>
        {capturing ? "Press a shortcut… (Esc to cancel)" : (
          <kbd className="font-[inherit]">{pretty(hotkey)}</kbd>
        )}
      </Button>
    </Card>
  );
}
```

- [ ] **Step 2: `MicrophoneCard.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import type { DeviceRef, Device } from "@/lib/types";
import { getMicLevel, startMicTest, stopMicTest } from "@/lib/bridge";
import { Button, Card, LevelMeter, Select } from "./fluent";

const id = (name: string, hostapi: string | null) => `${name}|${hostapi ?? ""}`;

export function MicrophoneCard({
  device, devices, error, onChange,
}: {
  device: DeviceRef | null;
  devices: Device[];
  error?: string;
  onChange: (d: DeviceRef | null) => void;
}) {
  const [testing, setTesting] = useState(false);
  const [level, setLevel] = useState(0);
  const [testError, setTestError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const stop = async () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setTesting(false);
    setLevel(0);
    try { await stopMicTest(); } catch { /* ignore */ }
  };

  const start = async () => {
    setTestError(null);
    const result = await startMicTest(device);
    if (!result.success) {
      setTestError(result.error ?? "Couldn't open the microphone");
      return;
    }
    setTesting(true);
    timer.current = window.setInterval(async () => {
      try { setLevel(await getMicLevel()); } catch { /* ignore */ }
    }, 60);
    window.setTimeout(stop, 15000);
  };

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); stopMicTest().catch(() => {}); }, []);

  const options = [
    { value: "__default__", label: "Windows default" },
    ...devices.map((d) => ({
      value: id(d.name, d.hostapi),
      label: d.is_default ? `${d.name} (default)` : d.name,
    })),
  ];

  return (
    <Card
      icon={Mic}
      title="Microphone"
      description="Voicemeeter buses and other virtual devices work too."
      error={error ?? testError}
      below={
        <div className="flex items-center gap-3">
          <Button onClick={testing ? stop : start}>{testing ? "Stop test" : "Test"}</Button>
          <div className="flex-1">
            <LevelMeter level={level} />
          </div>
        </div>
      }
    >
      <Select
        value={device ? id(device.name, device.hostapi) : "__default__"}
        options={options}
        onChange={(v) => {
          if (testing) stop();
          if (v === "__default__") return onChange(null);
          const d = devices.find((x) => id(x.name, x.hostapi) === v);
          if (d) onChange({ name: d.name, hostapi: d.hostapi });
        }}
      />
    </Card>
  );
}
```

- [ ] **Step 3: `DictionarySection.tsx`**

```bash
git mv shuper_whisper/ui/src/components/DictionaryTab.tsx shuper_whisper/ui/src/components/DictionarySection.tsx
```

Keep the component's state and handlers as they are. Restyle and relabel it:

1. Rename the exported component `DictionaryTab` → `DictionarySection`, and `DictionaryTabProps` → `DictionarySectionProps`.
2. Replace the outer `<div className="flex flex-col gap-4 h-full">` with `<div className="card divide-y divide-[var(--stroke)]">`.
3. Training banner:
   - change its wrapper class to `px-4 py-2.5 text-[12px] flex items-center gap-2`;
   - keep the colour logic, mapping `text-success`/`border-success/30` → `text-accent`, and `text-error`/`border-error/30` → `text-error`;
   - drop the `glass` and `border-*` classes;
   - replace the `animate-pulse-glow` class on the recording mic icon with `animate-pulse`.
4. Word list:
   - change the wrapper `flex-1 overflow-y-auto min-h-0` to `max-h-[280px] overflow-y-auto`;
   - change each row's classes from `glass rounded-lg px-3 py-2 ... hover:bg-white/[0.06]` to `px-4 py-2.5 flex items-center gap-3 group hover:bg-[var(--card-hover)]`;
   - change `space-y-1` to `divide-y divide-[var(--stroke)]`.
5. Below the word, show the hint as `<div className="text-[12px] text-muted truncate">sounds like “{entry.phonetic}”</div>` instead of the raw phonetic.
6. In every `<input>`, replace the classes `glass-input ... text-text-primary placeholder:text-text-muted/60` with `control h-8 px-2.5 text-[14px] placeholder:text-[var(--muted)]`.
7. Change the phonetic placeholders from `"Phonetic"` / `"Phonetic hint"` to `"Sounds like (optional)"`, and widen that input to `w-[170px]`.
8. Add-word form:
   - change its wrapper to `px-4 py-3 flex gap-2`;
   - change the add button to `btn-accent h-8 px-3 inline-flex items-center gap-1 text-[14px]`;
   - change its content to `<Plus size={14} /> Add`.
9. Empty state: change the texts to `No words yet` and `Add names or jargon ShuperWhisper keeps getting wrong.` Replace `text-text-muted` with `text-muted`.
10. Remaining colour classes:
    - icon-button hover classes `hover:text-accent hover:bg-accent/10` → `hover:bg-[var(--control-hover)]`;
    - `hover:text-error hover:bg-error/10` → `hover:text-error hover:bg-[var(--control-hover)]`;
    - `text-success` → `text-accent`.
11. In `BookIcon`, keep the SVG as it is.

After editing, run `rg -n "glass|text-text-|btn-ghost|animate-pulse-glow|text-success|bg-accent" shuper_whisper/ui/src`.
Expected: no matches.

- [ ] **Step 4: `ProcessingSection.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { Cpu, Type, Zap } from "lucide-react";
import type { AppConfig, GpuSetupProgress, GpuStatus } from "@/lib/types";
import { cancelGpuSetup, getGpuSetupProgress, getGpuStatus, setupGpu } from "@/lib/bridge";
import { Button, Card, LevelMeter, Select, Toggle } from "./fluent";

const FINISHED = ["done", "error", "cancelled"];

export function ProcessingSection({
  config, errors, apply, onGpuReady,
}: {
  config: AppConfig;
  errors: Partial<Record<keyof AppConfig, string>>;
  apply: (patch: Partial<AppConfig>) => Promise<void>;
  onGpuReady: () => void;
}) {
  const [gpu, setGpu] = useState<GpuStatus | null>(null);
  const [setup, setSetup] = useState<GpuSetupProgress | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = () => getGpuStatus().then(setGpu).catch(() => {});
  useEffect(() => {
    refresh();
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  const start = async () => {
    await setupGpu();
    timer.current = window.setInterval(async () => {
      const p = await getGpuSetupProgress();
      setSetup(p);
      if (FINISHED.includes(p.state)) {
        clearInterval(timer.current!);
        timer.current = null;
        await refresh();
        if (p.state === "done") onGpuReady();
      }
    }, 300);
  };

  const running = setup !== null && !FINISHED.includes(setup.state);
  let description: string;
  if (!gpu) description = "Checking…";
  else if (!gpu.gpu) description = "No NVIDIA graphics card found. Dictation runs on the processor.";
  else if (gpu.active) description = `${gpu.gpu}: in use`;
  else if (gpu.installed && config.compute === "cpu") description = `${gpu.gpu}: set up, but turned off below`;
  else if (gpu.installed) description = `${gpu.gpu}: set up, loading…`;
  else description = `${gpu.gpu} found. Download NVIDIA's libraries (about 1.3 GB) to turn on live typing.`;

  return (
    <>
      <Card
        icon={Zap}
        title="GPU acceleration"
        description={description}
        error={setup?.state === "error" ? setup.message : null}
        below={running && setup ? (
          <div className="flex flex-col gap-2">
            <LevelMeter level={setup.fraction * 0.15} />
            <span className="text-[12px] text-muted">
              {setup.message} {setup.state === "downloading" ? `${Math.round(setup.fraction * 100)}%` : ""}
            </span>
          </div>
        ) : undefined}
      >
        {gpu?.gpu && !gpu.installed && (
          running
            ? <Button onClick={() => cancelGpuSetup()}>Cancel</Button>
            : <Button variant="accent" onClick={start}>Set up</Button>
        )}
      </Card>
      <Card icon={Cpu} title="Use GPU when available"
            description="Turn off to always use the processor." error={errors.compute}>
        <Toggle label="Use GPU when available" checked={config.compute === "auto"}
                onChange={(on) => apply({ compute: on ? "auto" : "cpu" })} />
      </Card>
      <Card icon={Type} title="Live typing"
            description="Automatic types live with GPU acceleration, and all at once when you stop on the processor."
            error={errors.live_typing}>
        <Select
          value={config.live_typing}
          onChange={(v) => apply({ live_typing: v as AppConfig["live_typing"] })}
          options={[
            { value: "auto", label: "Automatic" },
            { value: "on", label: "Always live" },
            { value: "off", label: "Type when I stop" },
          ]}
        />
      </Card>
    </>
  );
}
```

`LevelMeter` treats 0.15 as full, which is why the fraction is scaled by 0.15.

- [ ] **Step 5: Rewrite `ui/src/App.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Cpu, Globe, Power } from "lucide-react";
import { useSettings } from "@/hooks/useSettings";
import { useTraining } from "@/hooks/useTraining";
import { getAutostart, setAutostart } from "@/lib/bridge";
import { Card, Section, Select, Toggle } from "@/components/fluent";
import { ShortcutCard } from "@/components/ShortcutCard";
import { MicrophoneCard } from "@/components/MicrophoneCard";
import { DictionarySection } from "@/components/DictionarySection";
import { ProcessingSection } from "@/components/ProcessingSection";

const MODEL_LABELS: Record<string, string> = {
  auto: "Automatic (recommended)",
  tiny: "Tiny (fastest)",
  base: "Base",
  small: "Small",
  medium: "Medium",
  "large-v3-turbo": "Large v3 Turbo",
  "large-v3": "Large v3 (most accurate)",
};

export default function App() {
  const { config, options, devices, system, status, loading, loadError, errors, apply, refreshSystem } = useSettings();
  const { trainingStatus, clearTraining } = useTraining();
  const [autostart, setAutostartState] = useState<boolean | null>(null);

  useEffect(() => { getAutostart().then(setAutostartState).catch(() => {}); }, []);

  if (loading) return <div className="p-6 text-muted text-[13px]">Loading…</div>;
  if (loadError || !config || !options) {
    return <div className="p-6 text-error text-[13px]">{loadError ?? "Couldn't load settings"}</div>;
  }

  const recognitionDescription =
    status.state === "loading" ? "Loading the speech model…" : system?.compute ?? "";

  return (
    <div className="h-full overflow-y-auto">
      <main className="max-w-[640px] mx-auto px-6 pt-6 pb-10">
        <h1 className="text-[28px] leading-9 font-semibold">ShuperWhisper</h1>
        {status.state === "error" && status.error && (
          <div className="card mt-4 px-4 py-3 text-[13px] text-error">{status.error}</div>
        )}

        <Section title="Dictation">
          <ShortcutCard hotkey={config.hotkey} error={errors.hotkey} onChange={(h) => apply({ hotkey: h })} />
          <MicrophoneCard
            device={config.input_device}
            devices={devices}
            error={errors.input_device}
            onChange={(d) => apply({ input_device: d })}
          />
        </Section>

        <Section title="Recognition">
          <Card icon={Cpu} title="Speech model" description={recognitionDescription} error={errors.model_size}>
            <Select
              value={config.model_size}
              disabled={status.state === "loading"}
              onChange={(v) => apply({ model_size: v })}
              options={options.models.map((m) => ({ value: m, label: MODEL_LABELS[m] ?? m }))}
            />
          </Card>
          <Card icon={Globe} title="Language" error={errors.language}>
            <Select
              value={config.language}
              onChange={(v) => apply({ language: v })}
              options={Object.entries(options.languages).map(([value, label]) => ({ value, label }))}
            />
          </Card>
        </Section>

        <Section title="Processing">
          <ProcessingSection config={config} errors={errors} apply={apply} onGpuReady={refreshSystem} />
        </Section>

        <Section title="Dictionary">
          <p className="text-[12px] text-muted mb-1">
            Words ShuperWhisper should know. If it keeps hearing a word wrong, put what it hears in
            “sounds like” and it will be swapped automatically. Train records you saying the word three times.
          </p>
          <DictionarySection trainingStatus={trainingStatus} clearTraining={clearTraining} />
        </Section>

        <Section title="General">
          <Card icon={Power} title="Start with Windows">
            {autostart !== null && (
              <Toggle
                label="Start with Windows"
                checked={autostart}
                onChange={async (on) => setAutostartState(await setAutostart(on))}
              />
            )}
          </Card>
        </Section>

        <p className="text-[12px] text-muted mt-6">Changes are saved automatically.</p>
      </main>
    </div>
  );
}
```

- [ ] **Step 6: Build**

```bash
cd shuper_whisper/ui && npm run build
```

Expected: no TypeScript errors.
- Fix any leftover imports of the deleted files: `useConfig`, `StyledSelect`, `TabNav`, `ActionBar`, `GeneralTab`.
- `lib/utils.ts` still exports `cn`, so leave it.

- [ ] **Step 6b: Look at it**

Run `python main.py`, then open Settings from the tray. Check:
- Light mode (Windows Settings → Personalisation → Colours → Light):
  - the light page, cards and accent;
  - a light title bar.
- Dark mode: the same, in dark, with a dark title bar.
- Pick Voicemeeter Out B1, then press **Test**. The meter moves when you speak.
- Pick a disconnected device. The Microphone card shows the error inline and the select reverts.
- Change the model to Small:
  - the description reads "Loading the speech model…" and the select is disabled;
  - afterwards it reads "Small on NVIDIA GeForce RTX 3080".
- Change the shortcut. Dictation uses the new one immediately.
- Toggle Start with Windows on and off.
- Processing section:
  - with the runtime installed, GPU acceleration reads "NVIDIA GeForce RTX 3080: in use";
  - turning off *Use GPU when available* reloads on the processor (the Speech model card reads "Small on CPU"), and turning it back on returns to the GPU;
  - *Live typing → Type when I stop* makes dictation appear all at once.
- Delete `%LOCALAPPDATA%\ShuperWhisper\cuda`, uninstall the pip extra, restart, then press **Set up**. The progress bar runs, and the card ends at "in use" without restarting the app.
- Resize the window to its minimum width. Nothing overflows horizontally.

- [ ] **Step 7: Commit tasks 6–8 together**

```bash
git add -A shuper_whisper/ui
git commit -m "feat(ui): one-page Windows 11 settings that apply instantly, with a mic level test"
```

---

### Task 9: Reproducible build

**Files:**
- Create: `packaging/build.py`
- Modify: `README.md`, project `CLAUDE.md` (local)

- [ ] **Step 1: Create `packaging/build.py`**

```python
"""Build dist/ShuperWhisper (PyInstaller one-folder) for packaging/installer.iss.

    python packaging/build.py

The CUDA runtime is never bundled: the installer offers to download it
(ShuperWhisper.exe --setup-gpu) when it finds an NVIDIA card.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, cwd=ROOT):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=(os.name == "nt" and cmd[0] == "npm"))


def main() -> None:
    run(["npm", "ci"], cwd=os.path.join(ROOT, "shuper_whisper", "ui"))
    run(["npm", "run", "build"], cwd=os.path.join(ROOT, "shuper_whisper", "ui"))
    run([sys.executable, "packaging/convert_icon.py"])
    run([sys.executable, "packaging/create_wizard_images.py"])
    # comtypes generates the UIAutomation wrapper on first use; do it now so
    # PyInstaller can bundle comtypes.gen.
    run([sys.executable, "-c", "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"])

    cmd = [
        sys.executable, "-m", "PyInstaller", "main.py",
        "--name", "ShuperWhisper", "--noconsole", "--noconfirm", "--onedir",
        "--icon", "packaging/ShuperWhisper.ico",
        "--add-data", f"shuper_whisper/ui/dist{os.pathsep}shuper_whisper/ui/dist",
        "--collect-data", "faster_whisper",
        "--collect-binaries", "ctranslate2",
        "--collect-submodules", "comtypes.gen",
        "--hidden-import", "comtypes.gen.UIAutomationClient",
        # Keep the pip CUDA wheels out even if they're installed in this env.
        "--exclude-module", "nvidia",
    ]
    run(cmd)
    print("\nBuilt dist/ShuperWhisper. Now compile packaging/installer.iss with Inno Setup.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 1b: Installer — GPU detection, download task, version 2.0.0**

In `packaging/installer.iss`:
- change `#define MyAppVersion "1.2.2"` to `"2.0.0"`;
- in `pyproject.toml`, set `version = "2.0.0"`.

Add to `[Tasks]`:

```
Name: "gpu"; Description: "Set up GPU acceleration for live typing (downloads about 1.3 GB from NVIDIA)"; GroupDescription: "NVIDIA graphics card found:"; Check: HasNvidiaGpu
```

Add this to `[Run]`, **above** the existing postinstall launch line:

```
Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup-gpu"; StatusMsg: "Setting up GPU acceleration..."; Tasks: gpu; Flags: waituntilterminated skipifsilent
```

Add a new section:

```
[UninstallDelete]
Type: filesandordirs; Name: "{app}\cuda"
Type: filesandordirs; Name: "{app}\cuda.partial"
```

At the top of `[Code]`, add:

```pascal
var
  NvidiaChecked: Boolean;
  NvidiaName: String;

{ First NVIDIA adapter's name via WMI, or '' when there is none. }
function NvidiaGpuName(): String;
var
  Locator, Service, Items, Item: Variant;
  I: Integer;
begin
  Result := '';
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Items := Service.ExecQuery('SELECT Name FROM Win32_VideoController');
    for I := 0 to Items.Count - 1 do
    begin
      Item := Items.ItemIndex(I);
      if Pos('NVIDIA', Uppercase(Item.Name)) > 0 then
      begin
        Result := Item.Name;
        Exit;
      end;
    end;
  except
    Result := '';
  end;
end;

function HasNvidiaGpu(): Boolean;
begin
  if not NvidiaChecked then
  begin
    NvidiaName := NvidiaGpuName();
    NvidiaChecked := True;
  end;
  Result := NvidiaName <> '';
end;
```

How it behaves:
- On a machine with an NVIDIA card, the task shows up ticked under "NVIDIA graphics card found:".
- Elsewhere, Inno hides it and the app runs on the processor.
- Upgrades keep `{app}\cuda`, because `[Files]` doesn't touch it, and `--setup-gpu` returns immediately when the pinned versions are already installed.

- [ ] **Step 2: Build and smoke-test**

```bash
python packaging/build.py
dist\ShuperWhisper\ShuperWhisper.exe
```

Check:
1. The tray icon appears.
2. The console-less log is silent. If it fails, run `dist\ShuperWhisper\ShuperWhisper.exe --console` from a terminal to see the error.
3. Settings opens styled, which proves `ui/dist` is bundled.
4. With no `dist\ShuperWhisper\cuda` folder, the app runs on the processor and types on stop. Settings → GPU acceleration offers **Set up**.
5. The pill appears under the caret, which proves the `comtypes.gen` UIA wrapper is bundled.

Then compile `packaging/installer.iss` in Inno Setup and run the installer on this machine. Check:
- the "Set up GPU acceleration" task is ticked;
- after the files are copied, the GPU setup window downloads and closes;
- the app launches with live typing, and Settings reads "… on NVIDIA GeForce RTX 3080";
- `%LOCALAPPDATA%\ShuperWhisper\cuda\runtime.json` exists.

Repeat checks 3–5. Uninstall, and confirm `%LOCALAPPDATA%\ShuperWhisper` is gone, including `cuda`.

If you can, run the installer on a machine without an NVIDIA card (or a VM). The GPU task should not appear, and dictation should type on stop.

- [ ] **Step 3: Docs**

README "Building from source":

```bash
pip install -e .[dev,gpu]
python packaging/build.py
```

then "compile `packaging/installer.iss` with Inno Setup".

Project `CLAUDE.md` Commands: replace the `python D:/dev/scripts/python_compiler/build.py --config compiler.toml` line with `python packaging/build.py   # PyInstaller one-folder build into dist/ShuperWhisper`.

- [ ] **Step 4: Commit, push, PR**

```bash
git add packaging/build.py packaging/installer.iss pyproject.toml README.md
git commit -m "build: PyInstaller build script; installer offers GPU setup on NVIDIA machines; v2.0.0"
git push -u origin feat/stage3-settings
source D:/dev/scripts/profile.sh && infisical-load-env && curl -sf -X POST \
  -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
  "$GITEA_URL/api/v1/repos/shuper/shuperwhisper/pulls" -d @- <<'EOF'
{"base":"main","head":"feat/stage3-settings","title":"Stage 3: Windows 11 settings page and reproducible build",
 "body":"Implements stage 3 of docs/superpowers/specs/2026-10-04-live-dictation-design.md.\n\n- One scrolling page of Fluent cards, follows system light/dark and accent colour\n- Changes apply instantly; errors shown on the card that caused them; model reloads in the background\n- Microphone test with a live level meter\n- Processing: GPU acceleration setup (pinned CUDA wheels from PyPI, hash-checked), Use GPU toggle, Live typing select\n- Installer detects an NVIDIA GPU and offers the download; build no longer bundles CUDA; v2.0.0\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"}
EOF
```

Never merge it.

- [ ] **Step 5: Whole-branch review**

Review the whole branch once, on the most capable model, against the spec's Stage 3 section and this plan (`git diff main...feat/stage3-settings`). Fix the findings on the same branch.

## Note on Mica

The spec allows a solid fallback for the Mica backdrop. This plan ships the solid Fluent page colours (`#f3f3f3` / `#202020`, the same colours Mica falls back to), because pywebview's WinForms host doesn't reliably let a DWM backdrop show through WebView2. If you want real Mica later, it's a self-contained follow-up:
- call `DwmSetWindowAttribute(hwnd, 38, 2)`;
- create the window with `transparent=True`;
- set the page background to `transparent`.
