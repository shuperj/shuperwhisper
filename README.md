# ShuperWhisper

**Hotkey-driven voice dictation for Windows.** Press a key, speak, press it again, and your words are typed wherever your cursor is.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for fast local transcription. No cloud, no subscription, no internet needed once the speech model has downloaded.

---

## How it works

- **Press once to start, press again to stop** (default `ctrl+shift+space`). Your words are typed at your cursor, in whatever app has focus, and your clipboard is never touched.
- **Live typing (with an NVIDIA GPU):** words appear as you speak, and the last few may adjust themselves as the sentence becomes clear, like dictation on a Mac. Click into another field mid-sentence and dictation carries on there; the first field is left alone. On a CPU-only PC the text is typed all at once when you stop (Settings can switch live typing on anyway).
- **A small pill under your cursor** shows that ShuperWhisper is listening. Dictation stops by itself after 30 seconds of silence.
- **Spoken commands:** "comma", "question mark", "exclamation point", "new line", "new paragraph", "period" and "colon" become the real thing. Pause briefly around "period", "colon" and "new line" so they aren't read as ordinary words ("a trial period").
- **Clean output:** single spaces, no em-dashes, and fillers like "um" and "uh" are dropped. Spacing and capitalisation follow what's already before your cursor.
- **Custom dictionary:** add names and jargon. If ShuperWhisper keeps mishearing a word, put what it hears in the hint and it's swapped automatically.
- **Any microphone,** including Voicemeeter buses and other virtual devices. Devices are remembered by name, so they survive restarts.
- **NVIDIA GPU** is used automatically once its libraries are set up (`large-v3-turbo` model), with a CPU fallback (`small` model). Settings can force the CPU. Intel/AMD integrated graphics aren't used; on those PCs it runs on the processor.

## Installation

Download `ShuperWhisper-Setup-x.x.x.exe` from [Releases](https://github.com/shuperj/shuperwhisper/releases) and run the installer.

Requires Windows 10/11 x64.

## Usage

1. ShuperWhisper starts in the system tray.
2. Click where you want the text, press your hotkey (default: `ctrl+shift+space`) and speak.
3. Press it again when you're done.
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

```bash
pip install -e .[dev]
python packaging/build.py      # settings UI, icons, then PyInstaller -> dist/ShuperWhisper/
```

Then compile `packaging/installer.iss` with [Inno Setup 6](https://jrsoftware.org/isinfo.php) to get
`dist/ShuperWhisper-Setup-<version>.exe`.

The installer stays small: NVIDIA's CUDA libraries are not bundled. When the
installer finds an NVIDIA graphics card it offers a ticked "Set up GPU
acceleration" option, which runs `ShuperWhisper.exe --setup-gpu` to download
them (about 1.2 GB, pinned versions from PyPI with checksums). Settings ->
Processing has the same button for later.

## Support

If you find ShuperWhisper useful, consider buying me a coffee:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/shuperj)

## Limits

- Windows doesn't let a normal app type into windows running as administrator (an elevated terminal, for example). ShuperWhisper says so in the pill instead of failing silently.
