**Workspace:** D:/dev (see ~/.devstack/config)
**Shared tooling:** check `D:/dev/scripts/INDEX.md` before building something new

# shuperwhisper (ShuperWhisper)

## Purpose
A hotkey-driven voice dictation app for Windows: hold a key, speak, release, and the transcribed text is typed at the cursor. Runs locally via faster-whisper with optional Claude-powered reformatting (email/AI-prompt modes), a system tray icon, and a floating waveform overlay.

## Stack
- Python 3.12+ (package `shuper_whisper`, entry `shuper_whisper.app:main`)
- faster-whisper (local transcription), sounddevice, numpy, pyperclip
- pystray (tray) + pywebview (overlay/UI), Pillow
- anthropic SDK (optional intelligent reformatting)
- pytest (+ pytest-mock, pytest-cov) for tests; PyInstaller for packaging

## Commands
```bash
pip install -e .[dev]                      # install with dev deps
cd shuper_whisper/ui && npm run build       # build settings UI (app needs ui/dist)
python main.py --console                    # run from source
pytest tests/ -x                            # run tests
python D:/dev/scripts/python_compiler/build.py --config compiler.toml  # build exe
```
Release also needs `packaging/convert_icon.py`, `packaging/create_wizard_images.py`,
then Inno Setup on `packaging/installer.iss`. Public steps are in README.md.

## Integrations
- Anthropic Claude API (optional) for reformatting dictated text
- Windows 10/11 x64 only; injects text at the active cursor

## Scope Notes
- Distributed as a Windows installer (`ShuperWhisper-Setup-x.x.x.exe`); version 1.2.2.
- Runtime files (config.json, dictionary.json, audio) and the `python-compiler/` toolkit are gitignored.
- A React UI lives under `shuper_whisper/ui/` (build artifacts gitignored).
