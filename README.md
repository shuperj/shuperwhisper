# ShuperWhisper

**Hotkey-driven voice dictation for Windows** — hold a key, speak, release, and your words are instantly typed wherever your cursor is.

Built on [faster-whisper](https://github.com/guillaumekientz/faster-whisper) for fast local transcription. No cloud, no subscription.

---

## Features

- **Hold-to-record** or **toggle mode** — choose your preferred hotkey style
- **Format modes** — Normal, Professional Email, AI Prompt (cycle with arrow keys)
- **Smart spacing** — auto-capitalises after punctuation, adapts to cursor context
- **Custom dictionary** — add words with phonetic hints and audio training
- **Floating overlay** — animated waveform while recording, spinning glow while processing
- **Tone settings** — dial in email formality and AI prompt detail levels
- **Claude API** — optional intelligent reformatting via Anthropic

## Installation

Download `ShuperWhisper-Setup-x.x.x.exe` from [Releases](https://github.com/shuperj/shuperwhisper/releases) and run the installer.

Requires Windows 10/11 x64.

## Usage

1. ShuperWhisper starts in the system tray
2. Hold your hotkey (default: `ctrl+shift+space`) to record
3. Release to transcribe and inject text at the cursor
4. Right-click the tray icon to open Settings or Quit

## Development

Requires Python 3.12+ and Node 18+ (the settings window is a React app).

```bash
# Install dependencies
pip install -e .[dev]

# Build the settings UI (required — the app loads shuper_whisper/ui/dist)
cd shuper_whisper/ui && npm install && npm run build && cd ../..

# Run from source
python main.py --console

# Run tests
pytest tests/ -x
```

### Building a release

1. Build the settings UI as above.
2. Generate the packaging assets (both are gitignored):
   ```bash
   python packaging/convert_icon.py        # -> packaging/ShuperWhisper.ico
   python packaging/create_wizard_images.py # -> packaging/*.bmp
   ```
3. Bundle with PyInstaller as a windowed **folder** build named `ShuperWhisper`,
   including `shuper_whisper/ui/dist` as data, so the result lands in
   `dist/ShuperWhisper/`.
4. Compile `packaging/installer.iss` with Inno Setup 6 to produce
   `dist/ShuperWhisper-Setup-<version>.exe`.

Step 3 is driven here by a private PyInstaller wrapper that isn't part of this
repo; any equivalent PyInstaller invocation producing `dist/ShuperWhisper/`
works.

## Support

If you find ShuperWhisper useful, consider buying me a coffee:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/shuperj)
