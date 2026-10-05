# ShuperWhisper v2: live, Mac-style dictation — design

Date: 2026-10-04 · Status: approved in chat, awaiting spec review

## Goal

Make ShuperWhisper behave like macOS dictation: tap a key, words appear live in
whatever field holds the cursor and revise themselves as you speak; click
somewhere else and dictation continues there. Strip everything that is not that.

Jared's complaints this addresses:

- The settings window and the onscreen indicator feel clunky.
- Selecting **Voicemeeter Out B1** (his mic bus) leaves the app stuck on "Loading".
- Output reads "AI-y": random double spaces, em-dashes, odd formatting.
- The email / AI-prompt transcription modes are bloat.

## Decisions

| Topic | Decision |
|---|---|
| Live insertion | **Fully inline, field-scoped.** Words are typed into the focused field as you speak; the still-changing tail is corrected in place. If focus changes or the user touches keyboard/mouse, the old field is left as-is and dictation continues at the new caret. |
| Formatting | **Rules only, no AI.** The Claude/anthropic dependency is removed. |
| Look | **Native Windows 11**: follows system light/dark and accent, Mica backdrop, Segoe UI Variable, one scrolling page. Indicator is a small pill at the text caret. |
| Hotkey | **Toggle only**: tap to start, tap to stop. |
| GPU vs CPU | NVIDIA GPU used when present and its runtime is installed; a **"Use GPU when available"** setting forces CPU-only. Intel/AMD iGPUs and NPUs are not used (CTranslate2 is CUDA-only). |
| Live typing | **Automatic** by default: live with a GPU, *type on stop* on CPU (more accurate `small` model, no lag). Settings has *Live typing: Automatic / On / Off*; live on CPU uses `base` (~1 s per update on a Ryzen 9 5900X, roughly 1.5–2 s on a laptop vPro i7). |
| GPU runtime | Not bundled. The installer detects an NVIDIA GPU and offers a pre-ticked **"GPU acceleration for live typing (~1.3 GB download)"** task; Settings has a **Set up GPU acceleration** button for later. Both use the same in-app downloader. |

## Root causes found

### Voicemeeter B1 stuck on "Loading"

Confirmed on Jared's machine with `sd.check_input_settings`:

1. `config.json` holds `input_device: 75`, which is Voicemeeter Out B1 on **WASAPI**.
   It accepts only 48 kHz in shared mode.
2. `audio.py` opens every device at a fixed 16 kHz, so `open_stream` raises
   `PortAudioError -9997 Invalid sample rate`.
3. `app.start()` has already set `STATE_LOADING` and aborts before `STATE_IDLE`,
   so the tray stays blue and the hotkey is never registered.
4. `bridge.save_config` writes the config first, then reloads. Its
   `{success: False}` result is ignored by `useConfig.ts`, and the window closes
   as if the save worked.
5. `reload_config` restarts only `if self._running`. After a failure `_running`
   is False, so choosing a working device later never restarts anything.
6. The bad index is already on disk, so every launch fails the same way.

Contributing problems:

- Devices are stored as PortAudio indices, which shift when Voicemeeter restarts
  or Bluetooth connects.
- The list shows every host-API duplicate (MME / DirectSound / WASAPI / WDM-KS)
  with no label to tell them apart.
- A device change reloads the Whisper model.

### Double spaces

- `transcriber.py` joins segments with `" ".join(segment.text …)`. Segments
  already start with a space, so every boundary gets two.
- `smart_text.apply_smart_spacing` prepends a space when the context is unknown
  or empty, and even when the text already starts with whitespace.

### Em-dashes

They come from the Claude formatter output and are never filtered.

### Injection

`injector.py` pastes through the clipboard (and never restores it). It probes
context with `Shift+Home`, `Ctrl+C`, `Right`, which has two bugs:

- It moves the cursor one character when nothing was selected.
- It selects the whole document if Ctrl is still held from the hotkey.

### GPU unused

The machine has an RTX 3080 and `ctranslate2.get_cuda_device_count() == 1`,
but `transcriber.py` hard-codes `cpu` / `int8`. CUDA is what makes live
re-transcription practical.

## Architecture

```
hotkey (toggle) ──► DictationSession
                      │
          AudioCapture (native rate → 16 kHz mono)
                      │ frames
          StreamingTranscriber (re-decode every ~400 ms, LocalAgreement-2, VAD utterances)
                      │ (stable words, tentative tail)
          text_rules (deterministic cleanup on stable text)
                      │
          LiveWriter (SendInput unicode, field-scoped revisions)
                      │
          CaretIndicator (pill at caret, level line)
```

Each unit has one job and a narrow interface:

- `AudioCapture`: `start(device_ref)`, `stop()`, `read_new()` → float32 16 kHz.
- `StreamingTranscriber`: takes audio and yields `Hypothesis(stable, tentative, final)`.
- `text_rules`: pure functions, `clean(text, context) -> str`.
- `LiveWriter`: `update(stable, tentative)` and `finish()`. It owns all
  keystrokes and the field-identity checks.
- `CaretIndicator`: `show()`, `hide()`, `set_level()`, `set_state()`.

## Stage 1 — Foundation: fixes and removals (PR 1)

The app is still batch (it transcribes on stop) at the end of this stage, but
the device bug, the text quality and the injection are all fixed.

### Audio (`audio.py`, `config.py`, `bridge.py`)

- **Device reference.** Store the device as `{"name": str, "hostapi": str}` or
  null for the system default.
  - Resolve it to an index at open time.
  - Refresh the PortAudio device list (`sd._terminate(); sd._initialize()`) when
    settings opens and after an open failure.
- **Migration.** An old integer `input_device` maps to name + hostapi if that
  index is still valid; otherwise it falls back to the default.
- **Device list.** `list_devices()`:
  - de-duplicates by name, preferring WASAPI > MME > DirectSound;
  - drops WDM-KS;
  - returns full names (MME truncates them at 31 characters) with a host-API label.
- **Opening.** Open at the device's native `default_samplerate`, mix down to
  mono, and resample to 16 kHz with `soxr` (new dependency).
  - If the native open fails, retry with `sd.WasapiSettings(auto_convert=True)`
    at 16 kHz.
- **Lifetime.** Open the stream on dictation start and close it on stop, so the
  Windows mic-in-use indicator is lit only while dictating.
- **Errors.** Check the callback `status`. If the stream dies mid-session, end
  the session and surface the error.

### App lifecycle (`app.py`)

- Add `STATE_ERROR` with a message, shown on the tray icon and in its tooltip.
- `start()` and `reload_config()` catch failures and land in `STATE_ERROR`;
  they never leave the app stuck in `STATE_LOADING`.
- Restarting no longer depends on `_running`.
- A device change reopens audio only; it never reloads the model.
- A new dictation cannot start while the previous one is still finishing.
- The transcribe/inject path runs inside `try/finally`.

### Transcriber (`transcriber.py`)

- New config `compute: "auto" | "cpu"`. With `auto`, pick `cuda`/`int8_float16`
  (`float16` on GPUs without int8 support) when
  `ctranslate2.get_cuda_device_count() > 0` **and** cuBLAS 12 + cuDNN 9
  load. Otherwise use `cpu`/`int8`. int8 weights halve the VRAM
  (large-v3-turbo: about 1.2 GB instead of 2.4 GB) at the same speed.
- The CUDA DLLs are searched for in the app's GPU runtime folder (see Stage 3)
  and in the pip `nvidia-*` wheels (dev installs via the `gpu` extra).
- Default model (`auto`): `large-v3-turbo` on GPU, `small` on CPU. Stage 2
  changes CPU-live to `base`. Every model stays selectable.
- Enable `vad_filter`.
- Join segments by stripping each one and separating them with a single space.

### Text rules (new `text_rules.py`; delete `smart_text.py`, `formatter.py`)

Deterministic and unit-tested:

1. Collapse whitespace runs to one space (newlines from commands are kept).
2. Strip the trailing `...` / `…` that Whisper adds at cut-offs.
3. Replace em/en dashes (`—`, `–`, and a spaced ` - ` used as a dash) with `, `.
   Hyphenated words are not touched.
4. Remove the standalone fillers `um`, `uh`, `erm`, `hmm`, case-insensitive,
   along with any comma that follows them. "like" and "just" are left alone.
5. Spoken commands:

   | Spoken | Inserted |
   |---|---|
   | "new line" | `\n` |
   | "new paragraph" | `\n\n` |
   | "period" | `.` |
   | "comma" | `,` |
   | "question mark" | `?` |
   | "exclamation point" / "exclamation mark" | `!` |
   | "colon" | `:` |

   Punctuation attaches to the previous word with no space before it.
6. Dictionary replacements, applied as find → replace, case-insensitive on
   whole words:
   - learned mishearings from training;
   - user-defined pairs.
7. Joining with what's already in the field:

   | Character before the caret | Leading space? | Capitalize? |
   |---|---|---|
   | non-whitespace, not an opening bracket or quote | yes | only if it is `.`, `!` or `?` |
   | `.`, `!` or `?` | yes | yes |
   | newline, or empty field | no | yes |
   | unknown | no | yes |

### Caret context (new `uia.py`)

Use UI Automation through `comtypes`: on the focused element, read
`TextPattern` → `GetSelection()[0]`, then expand to the line start to get the
text before the caret.

Fallback order:

1. UIA text before the caret.
2. The writer's own record of what it last typed into this field (same field
   identity).
3. Unknown.

### Injection (`injector.py`)

- Type with `SendInput` and `KEYEVENTF_UNICODE`; newlines go as `VK_RETURN`.
- Never touch the clipboard.
- Wait until the hotkey modifiers are physically up (`GetAsyncKeyState`, up to
  1 s) before sending.
- Delete the `Shift+Home` / `Ctrl+C` probe.

### Removals

- **Format modes:**
  - `VALID_FORMAT_MODES`, `FORMAT_MODE_*`, `email_tone`, `prompt_detail`;
  - the overlay format row;
  - the Up/Down arrow hotkey registration in `hotkey.py`;
  - format cycling in `app.py`.
- **Other config:** `bullet_mode`, `email_mode`, `hotkey_mode`, `accent_color`,
  `bg_color`.
- **Files:** `formatter.py`, `theme.py`.
- **Dependencies and keys:** the `anthropic` dependency, `.env` / API-key
  loading, and `pyperclip`.
- **Hotkey:** `HotkeyManager` keeps toggle behaviour only. The hold path and
  `_poll_release` are removed.
- **Config migration:** unknown keys in an old `config.json` are ignored on load.

**Settings UI in stage 1:** only the minimum needed to keep it consistent with
the config changes.

- Remove the Formatting tab and the colour pickers.
- Show the device list with host-API labels.
- Show save errors instead of closing the window.

The full redesign is stage 3.

## Stage 2 — Live inline dictation (PR 2)

### Live vs type-on-stop

- New config `live_typing: "auto" | "on" | "off"`. `auto` means live on GPU
  and type-on-stop on CPU.
- **Type-on-stop** keeps the stage 1 batch path: one beam-5 pass with VAD,
  fed to the writer as a single final hypothesis.
- **Auto model on CPU:** `base` when live, `small` when typing on stop.

### Streaming transcriber (new `streaming.py`)

- **Re-decode loop.** While dictating, a worker thread re-transcribes the
  current utterance buffer every `interval` (400 ms on GPU, 1 s on CPU).
  - It uses `word_timestamps=True`, with the committed text of the session as
    `initial_prompt`.
  - If one pass takes longer than the interval, the interval stretches to match.
- **LocalAgreement-2.** The longest common word prefix of the last two
  hypotheses is *stable*. Stable words never shrink. The rest of the newest
  hypothesis is the *tentative* tail.
- **Utterances.** VAD (faster-whisper's Silero) segments the stream.
  - After 700 ms of silence the utterance is finalized: everything becomes
    stable, the buffer is trimmed to after the utterance, and the next one starts.
  - Each decode stays bounded to one utterance, usually under 15 s. A hard cap
    of 25 s forces finalization.
- **Stop.** A final pass over the remaining audio, then everything is committed.
- **Auto-stop.** After 30 s of continuous silence the session ends.

### Live writer (new `live_writer.py`)

**State**

- `field_id`: foreground HWND plus the UIA focused-element RuntimeId.
- `committed_len`: characters this session has typed into the field.
- `typed_tail`: the tentative text currently in the field.

**`update(stable_delta, tentative)`**

1. Stable words go through `text_rules` with the caret context, then replace the
   matching prefix of `typed_tail`.
2. The new visible tail is `cleaned_stable_delta + normalized_tentative`.
3. Compute the common prefix with what is already typed, send backspaces for the
   rest of `typed_tail`, and type the new suffix.

**Field-scoped safety.** Before any backspace the writer checks that:

- the field identity is unchanged;
- no physical input arrived since the last write. Low-level keyboard and mouse
  hooks run while dictating; `LLKHF_INJECTED` / `LLMHF_INJECTED` events are
  ignored.
- if UIA can read the text before the caret, that text still ends with
  `typed_tail`.

If any check fails, the writer **freezes**:

- it leaves the old field alone;
- it resets `typed_tail`;
- it re-reads the caret context;
- it types the next words at the new caret.

It never backspaces more than its own tail.

**Known limit.** Elevated (admin) windows reject `SendInput` from a
non-elevated process (UIPI). The writer detects this (`SendInput` returns 0 or
the foreground process is elevated) and the indicator shows "Can't type into
admin windows".

### Caret indicator (rewrite `overlay.py`)

- **Shape.** A Fluent pill about 32 px tall: a mic glyph plus a thin live level
  line.
  - States: listening, finishing, and error with short text.
  - Follows the system light/dark theme.
- **Anchor.** Just below the text caret, re-anchored after each write. The caret
  position comes from, in order:
  1. `GetGUIThreadInfo(rcCaret)` mapped to screen coordinates;
  2. UIA `TextPattern` selection `GetBoundingRectangles`;
  3. bottom-centre of the focused window.
- **Existing code kept:** `WS_EX_NOACTIVATE`, the transparent-colour-key window
  and the per-monitor DPI handling.

## Stage 3 — Settings redesign (PR 3)

### Window (`tray.py`)

- Opened with pywebview at about 560 × 640, resizable.
- Mica backdrop via `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE=2)` with a
  transparent webview background. On Windows 10 it falls back to a solid
  background.
- The theme and accent come from `HKCU\...\Themes\Personalize\AppsUseLightTheme`
  and `DwmGetColorizationColor`, passed to the page.

### Page (`ui/`)

- One scrolling page of cards in the style of Windows 11 Settings.
- **Changes apply immediately**; there is no Save/Cancel.
- Errors show inline on the card that caused them.

Sections:

| Section | Contents |
|---|---|
| **Shortcut** | Hotkey capture. |
| **Microphone** | De-duplicated device list with host-API hint, plus a live level meter (a short test stream opened by the bridge) so you can confirm the mic works before closing. |
| **Recognition** | Model and language. Shows "GPU: NVIDIA GeForce RTX 3080" or "CPU". |
| **Dictionary** | Words, replacements and training. |
| **General** | Start with Windows. |

### Data and dependencies

- `useConfig.ts` handles `success: false` and puts a timeout on every bridge
  call. Devices are refreshed each time the window opens.
- Remove the unused `@radix-ui/react-slider`, `-switch` and `-tabs` packages,
  and `class-variance-authority`.

### GPU acceleration setup

**Downloader** (new `gpu_runtime.py`):

- Downloads the pinned `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` win_amd64
  wheels from PyPI. Versions and SHA-256 hashes are hard-coded and match what
  the bundled ctranslate2 was built against.
- Shows progress and can be cancelled.
- Verifies each hash, extracts only `nvidia/*/bin/*.dll` into the GPU
  runtime folder, and writes `runtime.json`. Re-running it is safe.
- **GPU runtime folder:** `<install dir>\cuda` when packaged (the installer
  is per-user, so it is writable), or `%LOCALAPPDATA%\ShuperWhisper\cuda`
  from source.

**Driver check:** if `nvidia-smi` reports a driver older than 525.60 (the
CUDA 12 minimum), it says "Update your NVIDIA driver" instead of downloading.

**Entry points:**

- `ShuperWhisper.exe --setup-gpu` opens a small progress window. The
  installer runs it.
- Settings → **Processing** shows the GPU status, a **Set up GPU
  acceleration** button with progress, the *Use GPU when available* toggle and
  the *Live typing* select.

**Installer (`installer.iss`):**

- A WMI query (`Win32_VideoController`) finds an NVIDIA card.
- The `gpu` task is shown and pre-ticked only when one is present.
- `[Run]` calls `--setup-gpu` for that task.
- `[UninstallDelete]` removes `{app}\cuda`.

**Build:** `packaging/build.py` no longer bundles any CUDA DLLs.

**Version:** bumped to 2.0.0.

## Testing

**Unit tests (pytest, every stage):**

- `text_rules`: double spaces, dashes vs hyphens, fillers, commands, every
  capitalization and spacing context, dictionary replacements.
- Device dedupe, resolution and migration, with a fake `query_devices`.
- The resampler: length and frequency sanity.
- Lifecycle: a failure lands in `STATE_ERROR`, and recovery works by choosing a
  good device.
- LocalAgreement diffing and utterance finalization, with scripted hypotheses.
- Live writer: backspace counts, freeze on focus change, freeze on physical
  input, freeze on context mismatch. Uses a fake injector and focus provider.

**Manual checks** (`python main.py --console`, with the UI built):

- Voicemeeter Out B1:
  - selecting it works and the meter moves;
  - after restarting Voicemeeter it still resolves.
- Live dictation into Notepad, a browser textarea, VS Code and Windows Terminal:
  - no double spaces or em-dashes;
  - the clipboard is untouched.
- Clicking into another field mid-dictation leaves the first field untouched and
  continues in the new one.
- The toggle hotkey works, and so does the 30 s silence auto-stop.
- Settings in light and dark; the indicator tracks the caret.

## Out of scope / known gaps

- `compiler.toml`, the `python_compiler` build config, is gitignored and not
  present on this machine. Stage 3 replaces it with a checked-in
  `packaging/build.py`.
- Intel/AMD integrated GPU or NPU acceleration (e.g. an OpenVINO backend).
  It's possible later, but it would mean a second inference engine.
- No TSF/IME composition-string integration. That would need a registered
  in-process text service, which is out of proportion for this app.
- macOS / Linux.
