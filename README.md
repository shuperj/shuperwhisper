# ShuperWhisper

**Hotkey-powered voice dictation for Windows.** Hold a key, speak, release — your words appear wherever your cursor is.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for fast, fully local speech-to-text. No cloud transcription, no latency, no subscriptions.

## Features

- **Smart hotkey** — Quick tap toggles recording on/off; holding records until you release. One hotkey, two modes, zero configuration.
- **Works everywhere** — Injects text into any focused text field via clipboard paste (browser, email, IDE, Slack, etc.)
- **Smart spacing** — Probes the text before your cursor and automatically adds spaces, capitalizes after sentences, and handles line breaks.
- **Format modes** — Cycle between Normal, Professional Email, and AI Prompt formatting with arrow keys while recording.
- **Tone controls** — Adjust email formality (warm to corporate) and prompt detail level (concise to comprehensive).
- **Custom dictionary** — Add specialized vocabulary with phonetic hints to improve recognition of names, jargon, and technical terms.
- **Floating overlay** — Minimal pill-shaped HUD shows a live waveform while recording and a spinning glow animation while processing.
- **System tray** — Runs quietly in the background with a color-coded tray icon (gray=idle, red=recording, orange=processing).
- **Settings UI** — Modern React-based settings panel accessible from the tray icon.
- **25 languages** — English, Spanish, French, German, Japanese, Chinese, and 19 more.
- **Multiple models** — Choose from `tiny` (fast) to `large-v3` (accurate) depending on your hardware.

## Install

### Option A: Download the release (recommended)

1. Download `ShuperWhisper-v1.0.0.zip` from [Releases](../../releases)
2. Extract to a folder (e.g. `C:\Programs\ShuperWhisper\`)
3. Run `ShuperWhisper.exe`
4. A gray circle appears in your system tray — ShuperWhisper is ready

> **First launch** downloads the Whisper model (~150 MB for `base`). This only happens once.

### Option B: Run from source

```
git clone <this-repo>
cd whisper-dictation
pip install -e ".[dev]"
python main.py
```

Requires Python 3.12+ and a working C compiler for `ctranslate2`.

## Usage

### Basic dictation

1. Focus any text field (browser, email, notepad, IDE)
2. Press **Ctrl+Shift+Space** (default hotkey)
3. Speak naturally
4. Release the hotkey (or press again if you tapped quickly)
5. Text appears at your cursor

### Smart hotkey behavior

The hotkey automatically detects your intent:

| Action | Behavior |
|--------|----------|
| **Hold** hotkey > 200ms, then release | Records while held, transcribes on release |
| **Quick tap** hotkey < 200ms | Enters toggle mode — press again to stop |

In toggle mode, the overlay shows your current format mode and you can cycle through modes with the **Up/Down arrow keys**.

### Format modes

| Mode | What it does |
|------|-------------|
| **Normal** | Direct transcription with smart spacing |
| **Professional Email** | Reformats speech into a polished email (uses Claude API if available, otherwise template fallback) |
| **AI Prompt** | Cleans filler words, structures text as an AI prompt |

Format modes work without an API key using built-in templates. Adding a [Claude API key](https://console.anthropic.com/) enables intelligent reformatting with tone and detail controls.

### Custom dictionary

Open **Settings > Dictionary** to add words that Whisper frequently gets wrong:

| Field | Example | Purpose |
|-------|---------|---------|
| Word | `Kubernetes` | The correct spelling |
| Phonetic | `koo-ber-net-eez` | Helps Whisper recognize pronunciation |

You can also train words by recording yourself saying them — ShuperWhisper will verify recognition.

## Configuration

Right-click the tray icon and select **Settings** to configure:

| Setting | Default | Options |
|---------|---------|---------|
| Hotkey | `Ctrl+Shift+Space` | Any key combination (click to capture) |
| Model | `base` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| Language | English | 25 languages + auto-detect |
| Smart spacing | On | Auto-spacing and capitalization |
| Overlay position | Top center | Top, center, or bottom of screen |
| Accent color | `#ff4466` | Overlay and UI accent color |
| Background color | `#1a1a2e` | Overlay background |

Configuration is stored in `%APPDATA%\ShuperWhisper\config.json` (exe) or `config.json` in the project root (dev mode).

## Model sizes

| Model | Size | Speed | Accuracy | RAM |
|-------|------|-------|----------|-----|
| `tiny` | 75 MB | Fastest | Good for clear speech | ~1 GB |
| `base` | 150 MB | Fast | Good balance (default) | ~1 GB |
| `small` | 500 MB | Moderate | Better accuracy | ~2 GB |
| `medium` | 1.5 GB | Slower | High accuracy | ~5 GB |
| `large-v3` | 3 GB | Slowest | Best accuracy | ~10 GB |

Models are downloaded automatically on first use and cached locally.

## Architecture

```
main.py                    Entry point (console or tray mode)
shuper_whisper/
  app.py                   State machine: idle -> recording -> processing
  audio.py                 Audio capture via sounddevice
  transcriber.py           faster-whisper speech-to-text
  hotkey.py                Global hotkey with smart hold/toggle
  injector.py              Clipboard paste + context probing
  smart_text.py            Spacing, bullets, email formatting
  formatter.py             Claude API + template text formatting
  dictionary.py            Custom vocabulary with phonetic hints
  overlay.py               Floating pill HUD (pywebview + CSS)
  config.py                JSON config with AppData support
  tray.py                  System tray + HTTP server for UI
  bridge.py                Python <-> React communication
  settings_ui.py           Legacy tkinter settings (unused)
  theme.py                 UI color definitions
  autostart.py             Windows registry autostart
  ui/                      React + Vite + Tailwind settings panel
```

## Requirements

- Windows 10/11
- A microphone
- ~1 GB RAM (for `base` model)
- No GPU required (runs on CPU via CTranslate2)
- Optional: [Claude API key](https://console.anthropic.com/) for AI-powered formatting

## License

MIT
