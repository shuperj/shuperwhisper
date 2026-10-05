"""Main application orchestrator and process entry point for ShuperWhisper."""

import ctypes
import multiprocessing
import sys
import threading
from typing import Callable, Optional

import numpy as np

from . import audio_devices, uia
from ._win32_keys import InjectionBlocked
from .audio import AudioRecorder
from .config import AppConfig, load_config, save_config
from .dictionary import WordDictionary
from .hotkey import HotkeyManager
from .injector import TextInjector
from .overlay import RecordingOverlay
from .text_rules import clean
from .transcriber import Transcriber

STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_LOADING = "loading"
STATE_ERROR = "error"

# If even the loudest 100 ms of a recording is below this RMS, it's silence
# (Whisper hallucinates on silence).
SILENCE_RMS_THRESHOLD = 0.005


def is_silent(audio: Optional[np.ndarray]) -> bool:
    if audio is None or len(audio) == 0:
        return True
    window = 1600  # 100 ms at 16 kHz
    usable = len(audio) // window * window or len(audio)
    frames = audio[:usable].reshape(-1, min(window, usable))
    loudest = float(np.sqrt(np.mean(frames ** 2, axis=1)).max())
    return loudest < SILENCE_RMS_THRESHOLD


class ShuperWhisperApp:
    """Wires together audio, transcription, the hotkey, the overlay and typing."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.error: Optional[str] = None
        self._state_callback: Optional[Callable[[str], None]] = None
        self._running = False
        self._session_lock = threading.Lock()
        self._level_timer: Optional[threading.Timer] = None

        self.recorder = AudioRecorder(device_ref=config.input_device)
        self.transcriber = Transcriber(model_size=config.model_size, language=config.language,
                                       compute=config.compute)
        self.injector = TextInjector()
        self.hotkey_manager = self._make_hotkeys(config.hotkey)
        self.dictionary = WordDictionary()
        self.overlay = RecordingOverlay(position=config.overlay_position)

    # -- state ---------------------------------------------------------------

    def set_state_callback(self, callback: Callable[[str], None]) -> None:
        self._state_callback = callback

    def _set_state(self, state: str, error: Optional[str] = None) -> None:
        self.error = error
        if self._state_callback:
            self._state_callback(state)

    def _fail(self, message: str) -> None:
        print(f"[app] ERROR: {message}", flush=True)
        self._set_state(STATE_ERROR, message)

    def _make_hotkeys(self, hotkey: str) -> HotkeyManager:
        return HotkeyManager(hotkey, on_start=self._on_record_start, on_stop=self._on_record_stop)

    def _run_async(self, fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    # -- dictation session -----------------------------------------------------

    def _on_record_start(self) -> None:
        if not self._session_lock.acquire(blocking=False):
            self.hotkey_manager.reset()  # previous dictation is still being typed
            return
        try:
            self.recorder.start_recording()
        except Exception as e:
            self._session_lock.release()
            self.hotkey_manager.reset()
            self._fail(f"Microphone: {e}")
            return
        self._set_state(STATE_RECORDING)
        self.overlay.show()
        self._start_level_monitoring()

    def _on_record_stop(self) -> None:
        self._stop_level_monitoring()
        try:
            audio = self.recorder.stop_recording()
        except Exception as e:
            audio = None
            self.recorder.stream_error = str(e)
        self._set_state(STATE_PROCESSING)
        self.overlay.show_processing()
        self._run_async(self._finish_session, audio)

    def _finish_session(self, audio: Optional[np.ndarray]) -> None:
        try:
            if self.recorder.stream_error:
                raise RuntimeError(self.recorder.stream_error)
            if is_silent(audio):
                self._set_state(STATE_IDLE)
                return
            text = self.transcriber.transcribe(
                audio,
                initial_prompt=self.dictionary.get_initial_prompt() or None,
                hotwords=self.dictionary.get_hotwords() or None,
            )
            text = clean(text, self.dictionary.get_replacements())
            if text:
                self.injector.inject(text)
            self._set_state(STATE_IDLE)
        except InjectionBlocked as e:
            self._fail(str(e))
        except Exception as e:
            self._fail(f"Dictation failed: {e}")
        finally:
            self.overlay.hide()
            self._session_lock.release()

    def _start_level_monitoring(self) -> None:
        def _update():
            if self.recorder.check_alive():
                # Device vanished mid-dictation: end the session now rather
                # than waiting for the second hotkey press.
                self._level_timer = None
                self.hotkey_manager.reset()
                self._run_async(self._on_record_stop)
                return
            if self.overlay.is_visible:
                self.overlay.update_levels(self.recorder.get_levels(self.overlay.BAR_COUNT))
                self._level_timer = threading.Timer(0.033, _update)
                self._level_timer.daemon = True
                self._level_timer.start()
        _update()

    def _stop_level_monitoring(self) -> None:
        if self._level_timer:
            self._level_timer.cancel()
            self._level_timer = None

    # -- lifecycle -------------------------------------------------------------

    def _migrate_device(self) -> None:
        migrated = audio_devices.migrate(self.config.input_device)
        if migrated != self.config.input_device:
            self.config.input_device = migrated
            self.recorder = AudioRecorder(device_ref=migrated)
            save_config(self.config)

    def start(self) -> None:
        """Load the model and register the hotkey. Never raises; failures
        leave the app in STATE_ERROR with ``self.error`` set."""
        if self._running:
            return
        self._set_state(STATE_LOADING)
        uia.warm_up()
        try:
            self._migrate_device()
            if not self.transcriber.loaded:
                self.transcriber.load_model()
            self.hotkey_manager.register()
        except Exception as e:
            self._fail(str(e))
            return
        self._running = True
        self._set_state(STATE_IDLE)
        print(f"[app] Ready. Press {self.config.hotkey} to dictate.", flush=True)

    def shutdown(self, destroy_overlay: bool = True) -> None:
        self._stop_level_monitoring()
        self.hotkey_manager.unregister()
        if destroy_overlay:
            self.overlay.destroy()
        else:
            self.overlay.hide()
        self._running = False

    @property
    def busy(self) -> bool:
        """A dictation is being recorded or typed."""
        return self._session_lock.locked()

    def reload_config(self, new_config: AppConfig) -> bool:
        """Apply settings, touching only what differs from what's running.

        Never raises. Returns False without changing anything while a
        dictation is in progress.
        """
        if not self._session_lock.acquire(blocking=False):
            return False
        try:
            self._apply_config(new_config)
        finally:
            self._session_lock.release()
        return True

    def _apply_config(self, new_config: AppConfig) -> None:
        self.config = new_config
        self.dictionary.load()
        self.overlay.set_position(new_config.overlay_position)
        try:
            # Compare with what's actually running, not the previous config:
            # an earlier failed reload may have left them different.
            if new_config.input_device != self.recorder.device_ref:
                self.recorder = AudioRecorder(device_ref=new_config.input_device)
            model_changed = (new_config.model_size, new_config.compute) != self.transcriber.requested
            if model_changed or not self.transcriber.loaded:
                self._set_state(STATE_LOADING)
                self.transcriber = Transcriber(model_size=new_config.model_size,
                                               language=new_config.language,
                                               compute=new_config.compute)
                self.transcriber.load_model()
            self.transcriber.language = new_config.language
            if new_config.hotkey != self.hotkey_manager.hotkey or not self.hotkey_manager.registered:
                self.hotkey_manager.unregister()
                self.hotkey_manager = self._make_hotkeys(new_config.hotkey)
                self.hotkey_manager.register()
        except Exception as e:
            self._fail(str(e))
            return
        self._running = True
        self._set_state(STATE_IDLE)

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self) -> None:
        """Console mode: start, then block until Ctrl+C."""
        self.start()
        if not self._running:
            return
        try:
            self.hotkey_manager.wait()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.shutdown()


def list_devices() -> None:
    """Print available audio input devices and exit."""
    print("Available audio input devices:\n")
    for d in audio_devices.list_input_devices():
        default = " (DEFAULT)" if d.is_default else ""
        print(f"  {d.name}  [{d.to_dict()['hostapi_label']}, {int(d.samplerate)} Hz]{default}")


def _enable_dpi_awareness() -> None:
    """Declare per-monitor DPI awareness so Win32 APIs return real pixels.

    Without this the floating recording overlay is mispositioned and blurry on
    scaled displays.
    """
    try:
        # Windows 10 1703+ -- per-monitor v2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Older fallback -- system DPI aware
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    """Entry point for the installed ``shuper-whisper`` gui-script; main.py delegates here (issue #11)."""
    multiprocessing.freeze_support()
    _enable_dpi_awareness()

    if "--list-devices" in sys.argv:
        list_devices()
        sys.exit(0)

    config = load_config()

    if "--console" in sys.argv:
        app = ShuperWhisperApp(config)
        app.run()
    else:
        # Imported here, not at module scope: tray.py imports from this module,
        # so a top-level import would be circular.
        from .tray import TrayController

        tray = TrayController(config)
        tray.run()
