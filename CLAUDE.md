**Workspace:** D:/dev (see ~/.devstack/config)
**Shared tooling:** check `D:/dev/scripts/INDEX.md` before building something new

# shuperwhisper (ShuperWhisper)

## Purpose
A hotkey-driven voice dictation app for Windows: press a key, speak, press again, and the transcribed text is typed at the cursor. Runs locally via faster-whisper (CUDA when available, CPU fallback), deterministic text cleanup (no AI), a system tray icon, and a small recording overlay.

## Stack
- Python 3.12+ (package `shuper_whisper`, entry `shuper_whisper.app:main`)
- faster-whisper (local transcription), sounddevice + soxr (capture/resample), numpy, comtypes (UI Automation)
- pystray (tray) + pywebview (overlay/UI), Pillow
- pytest (+ pytest-mock, pytest-cov) for tests; PyInstaller for packaging

## Commands
```bash
pip install -e .[dev,gpu]                  # install with dev deps (+ CUDA runtime)
cd shuper_whisper/ui && npm run build       # build settings UI (app needs ui/dist)
python main.py --console                    # run from source
pytest tests/ -x                            # run tests
python packaging/build.py                  # PyInstaller one-folder build into dist/ShuperWhisper
```
Then Inno Setup on `packaging/installer.iss`. The CUDA runtime is downloaded on
demand (`--setup-gpu`, `shuper_whisper/gpu_runtime.py`), never bundled.
Releases: tag `vX.Y.Z` on main, then `gh release create` on `shuperj/shuperwhisper`
(GitHub, mirrored from Gitea) with the installer and a zip of `dist/ShuperWhisper`.
Model choice and live-typing tuning: `benchmarks/` (README there; results in `benchmarks/results/`).

## Integrations
- Windows 10/11 x64 only; injects text at the active cursor

## Scope Notes
- Distributed as a Windows installer (`ShuperWhisper-Setup-x.x.x.exe`); version 2.1.0.
- Runtime files (config.json, dictionary.json, audio) and the `python-compiler/` toolkit are gitignored.
- A React UI lives under `shuper_whisper/ui/` (build artifacts gitignored).
- Design: docs/superpowers/specs/2026-10-04-live-dictation-design.md (stage plans in docs/superpowers/plans/).
