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
- **Packaging.** A checked-in `packaging/build.py` drives PyInstaller in one-folder mode, producing `dist/ShuperWhisper` for the existing Inno Setup script.

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

### Task 2: Bridge — status, system info, mic test, background model reload

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

- [ ] **Step 1: Track the current state in the app**

In `shuper_whisper/app.py`:
- add `self.state = STATE_IDLE` to `ShuperWhisperApp.__init__`;
- add `self.state = state` as the first line of `_set_state`.

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


def test_mic_test_error(api, monkeypatch):
    monkeypatch.setattr(bridge_mod, "AudioRecorder", FakeRecorder)
    result = api.start_mic_test({"name": "Broken", "hostapi": None})
    assert result == {"success": False, "error": "Invalid sample rate"}
    assert api.get_mic_level() == 0.0
```

Run: `python -m pytest tests/test_bridge_settings.py -q`
Expected: FAIL (the new methods don't exist).

- [ ] **Step 3: Add `gpu_name` to `transcriber.py`**

```python
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
from . import system_theme
from .audio import AudioRecorder
from .transcriber import gpu_name

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

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shuper_whisper/bridge.py shuper_whisper/transcriber.py shuper_whisper/app.py tests/test_bridge_settings.py
git commit -m "feat(bridge): system info, status polling, mic test, background model reload"
```

---

### Task 3: Settings window chrome

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

### Task 4: Fluent styles and primitives

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

The build is broken until Task 6 rewrites `App.tsx`, so don't commit yet. Continue straight into Task 5.

---

### Task 5: Settings data hook

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
```

In `save_config`'s return type, add `loading?: boolean`, and change the `saveConfig` wrapper's return type to match. Import `AppStatus`, `SystemInfo` and `DeviceRef` from `./types`.

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

Continue into Task 6; there is no commit yet.

---

### Task 6: The settings page

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

- [ ] **Step 4: Rewrite `ui/src/App.tsx`**

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
  const { config, options, devices, system, status, loading, loadError, errors, apply } = useSettings();
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

- [ ] **Step 5: Build**

```bash
cd shuper_whisper/ui && npm run build
```

Expected: no TypeScript errors.
- Fix any leftover imports of the deleted files: `useConfig`, `StyledSelect`, `TabNav`, `ActionBar`, `GeneralTab`.
- `lib/utils.ts` still exports `cn`, so leave it.

- [ ] **Step 6: Look at it**

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
- Resize the window to its minimum width. Nothing overflows horizontally.

- [ ] **Step 7: Commit tasks 4–6 together**

```bash
git add -A shuper_whisper/ui
git commit -m "feat(ui): one-page Windows 11 settings that apply instantly, with a mic level test"
```

---

### Task 7: Reproducible build

**Files:**
- Create: `packaging/build.py`
- Modify: `README.md`, project `CLAUDE.md` (local)

- [ ] **Step 1: Create `packaging/build.py`**

```python
"""Build dist/ShuperWhisper (PyInstaller one-folder) for packaging/installer.iss.

    python packaging/build.py          # CPU + GPU runtime if the nvidia wheels are installed
    python packaging/build.py --cpu    # leave the CUDA runtime out (~1 GB smaller)
"""

import argparse
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, cwd=ROOT):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=(os.name == "nt" and cmd[0] == "npm"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", action="store_true", help="omit the CUDA runtime")
    args = parser.parse_args()

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
    ]
    if not args.cpu and importlib.util.find_spec("nvidia") is not None:
        cmd += ["--collect-binaries", "nvidia.cublas", "--collect-binaries", "nvidia.cudnn"]
    run(cmd)
    print("\nBuilt dist/ShuperWhisper. Now compile packaging/installer.iss with Inno Setup.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Build and smoke-test**

```bash
python packaging/build.py
dist\ShuperWhisper\ShuperWhisper.exe
```

Check:
1. The tray icon appears.
2. The console-less log is silent. If it fails, run `dist\ShuperWhisper\ShuperWhisper.exe --console` from a terminal to see the error.
3. Settings opens styled, which proves `ui/dist` is bundled.
4. Dictation is live, and Settings → Speech model reads "… on NVIDIA GeForce RTX 3080", which proves the CUDA DLLs are bundled and found through `_MEIPASS/nvidia/*/bin`.
5. The pill appears under the caret, which proves the `comtypes.gen` UIA wrapper is bundled.

Then compile `packaging/installer.iss` in Inno Setup. Install, launch from the Start menu, and repeat checks 3–5.

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
git add packaging/build.py README.md
git commit -m "build: checked-in PyInstaller build script with optional CUDA runtime"
git push -u origin feat/stage3-settings
source D:/dev/scripts/profile.sh && infisical-load-env && curl -sf -X POST \
  -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
  "$GITEA_URL/api/v1/repos/shuper/shuperwhisper/pulls" -d @- <<'EOF'
{"base":"main","head":"feat/stage3-settings","title":"Stage 3: Windows 11 settings page and reproducible build",
 "body":"Implements stage 3 of docs/superpowers/specs/2026-10-04-live-dictation-design.md.\n\n- One scrolling page of Fluent cards, follows system light/dark and accent colour\n- Changes apply instantly; errors shown on the card that caused them; model reloads in the background\n- Microphone test with a live level meter\n- packaging/build.py: PyInstaller one-folder build, bundles CUDA runtime when available\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"}
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
