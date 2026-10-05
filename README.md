# ShuperWhisper

**Hotkey-driven voice dictation for Windows.** Press a key, speak, press it again, and your words are typed wherever your cursor is.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for fast local transcription. No cloud, no subscription, no internet needed once the speech model has downloaded.

---

## How it works

- **Press once to start, press again to stop** (default `ctrl+shift+space`). The text is typed at your cursor, in whatever app has focus. Your clipboard is never touched.
- **Spoken commands:** "new line", "new paragraph", "period", "comma", "question mark", "exclamation point" and "colon" become the real thing.
- **Clean output:** single spaces, no em-dashes, and fillers like "um" and "uh" are dropped. Spacing and capitalisation follow what's already before your cursor.
- **Custom dictionary:** add names and jargon. If ShuperWhisper keeps mishearing a word, put what it hears in the hint and it's swapped automatically.
- **Any microphone,** including Voicemeeter buses and other virtual devices. Devices are remembered by name, so they survive restarts.
- **NVIDIA GPU** is used automatically when present (`large-v3-turbo` model), with a CPU fallback (`small` model). Settings can force the CPU.

## Installation

Download `ShuperWhisper-Setup-x.x.x.exe` from [Releases](https://github.com/shuperj/shuperwhisper/releases) and run the installer.

Requires Windows 10/11 x64.

## Usage

1. ShuperWhisper starts in the system tray.
2. Press your hotkey (default: `ctrl+shift+space`) and speak.
3. Press it again; the text is typed at your cursor.
4. Right-click the tray icon to open Settings or Quit.

The tray icon is grey when idle, red while listening, amber while transcribing, blue while loading the model and dark red on an error. Hover it to see the error message.

## Development

Requires Python 3.12+ and Node 18+ (the settings window is a React app).

```bash
# Install dependencies (the gpu extra adds NVIDIA's CUDA runtime; skip it for CPU-only)
pip install -e .[dev,gpu]

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
