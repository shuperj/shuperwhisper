"""Main application orchestrator and process entry point for ShuperWhisper."""

import ctypes
import multiprocessing
import sys
import threading
import time
from typing import Callable, Optional

import numpy as np

from . import audio_devices, gpu_runtime, uia
from ._win32_keys import MODIFIER_VK_MAP, InjectionBlocked, get_vk
from .audio import AudioRecorder
from .config import AppConfig, config_dir, load_config, save_config
from .dictionary import WordDictionary
from .hotkey import HotkeyManager, parse_hotkey
from .live_writer import LiveWriter
from .overlay import CaretIndicator
from .streaming import Hypothesis, StreamingSession
from .transcriber import Transcriber

STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_LOADING = "loading"
STATE_ERROR = "error"

# Stop by itself after this long without speech (live mode: StreamingSession).
AUTO_STOP_SECONDS = 30.0

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


class _Dictation:
    """One press-to-press dictation."""

    def __init__(self):
        self.session: Optional[StreamingSession] = None
        self.stopping = False
        self.field = None  # where the indicator was placed


class ShuperWhisperApp:
    """Wires together audio, transcription, the hotkey, the indicator and typing.

    With live typing (the default on a GPU) a StreamingSession feeds words to
    the LiveWriter as you speak; otherwise one accurate pass runs when you stop.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.error: Optional[str] = None
        self.reload_error: Optional[str] = None  # what the last settings change couldn't apply
        self.state = STATE_IDLE
        self._state_callback: Optional[Callable[[str], None]] = None
        self._running = False
        self._session_lock = threading.Lock()
        self._token_lock = threading.Lock()
        self._current: Optional[_Dictation] = None
        self._session_error: Optional[str] = None

        self.recorder = AudioRecorder(device_ref=config.input_device)
        self.transcriber = Transcriber(model_size=config.model_size, language=config.language,
                                       compute=config.compute, live_typing=config.live_typing)
        self.hotkey_manager = self._make_hotkeys(config.hotkey)
        self.dictionary = WordDictionary()
        self.writer = LiveWriter(replacements=lambda: self.dictionary.get_replacements())
        self.overlay = CaretIndicator()

    # -- state ---------------------------------------------------------------

    def set_state_callback(self, callback: Callable[[str], None]) -> None:
        self._state_callback = callback

    def _set_state(self, state: str, error: Optional[str] = None) -> None:
        self.state = state
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

    def _hotkey_keys(self) -> tuple[list[int], int]:
        """(modifier VKs, trigger VK) of the configured hotkey."""
        modifiers, trigger = parse_hotkey(self.config.hotkey)
        vks: list[int] = []
        for mod in modifiers:
            vks.extend(MODIFIER_VK_MAP.get(mod, []))
        return vks, get_vk(trigger)

    # -- dictation session -----------------------------------------------------
    #
    # Each dictation is a _Dictation token. Every way a dictation can end (the
    # hotkey, auto-stop, a dead mic, the session finishing by itself) goes
    # through the token, so a late or duplicate stop can't touch the next
    # dictation, and the session lock is released exactly once.

    def _on_record_start(self) -> None:
        if not self._session_lock.acquire(blocking=False):
            self.hotkey_manager.reset()  # previous dictation is still finishing
            return
        token = _Dictation()
        try:
            self.recorder.start_recording()
        except Exception as e:
            self._session_lock.release()
            self.hotkey_manager.reset()
            self._fail(f"Microphone: {e}")
            self.overlay.show_error(self.error)
            return
        try:
            with self._token_lock:
                self._current = token
            self._session_error = None
            modifiers, trigger = self._hotkey_keys()
            self.writer.begin(ignore_vks=modifiers, trigger_vk=trigger)
            self._set_state(STATE_RECORDING)
            self.overlay.show()
            token.field = self.writer.field
            if self.transcriber.live:
                token.session = StreamingSession(
                    transcriber=self.transcriber,
                    read_audio=self.recorder.read_new,
                    on_hypothesis=lambda h: self._on_hypothesis(h, token),
                    on_finished=lambda error: self._on_session_finished(error, token),
                    on_auto_stop=lambda: self._auto_stop(token),
                    prompt=self.dictionary.get_initial_prompt,
                    hotwords=self.dictionary.get_hotwords() or None,
                    interval=0.4 if self.transcriber.device == "cuda" else 1.0,
                )
            self._start_level_monitoring(token)
            if token.session:
                token.session.start()
            # else type-on-stop: _on_record_stop runs one accurate pass
        except Exception as e:
            self._on_session_finished(f"Couldn't start dictation: {e}", token)

    @property
    def _session(self) -> Optional[StreamingSession]:
        current = self._current
        return current.session if current else None

    def _on_hypothesis(self, hypothesis: Hypothesis, token: "_Dictation") -> None:
        if token is not self._current or self._session_error:
            return
        try:
            self.writer.update(hypothesis.stable_delta, hypothesis.tentative,
                               final=hypothesis.final)
        except InjectionBlocked as e:
            self._session_error = str(e)
            self._on_record_stop(token)
            return
        if self.writer.field != token.field:  # dictation moved to another field
            token.field = self.writer.field
            self.overlay.reposition(use_uia=True)

    def _on_record_stop(self, token: Optional["_Dictation"] = None) -> None:
        """Stop the current dictation (or ``token``'s, if it's still current)."""
        with self._token_lock:
            current = self._current
            if current is None or (token is not None and token is not current) or current.stopping:
                return
            current.stopping = True
        self._set_state(STATE_PROCESSING)
        self.overlay.set_state("finishing")
        if current.session:
            current.session.stop()
        else:
            self._run_async(self._finish_batch, current)

    def _auto_stop(self, token: "_Dictation") -> None:
        self.hotkey_manager.reset()
        self._on_record_stop(token)

    def _finish_batch(self, token: "_Dictation") -> None:
        """Type-on-stop: one beam-5 pass with VAD over the whole recording."""
        error = None
        try:
            audio = self.recorder.stop_recording()
            if not self.recorder.stream_error and not is_silent(audio):
                text = self.transcriber.transcribe(
                    audio,
                    initial_prompt=self.dictionary.get_initial_prompt() or None,
                    hotwords=self.dictionary.get_hotwords() or None,
                )
                if text:
                    self._on_hypothesis(Hypothesis(text, "", True), token)
        except Exception as e:
            error = str(e)
        self._on_session_finished(error, token)

    def _on_session_finished(self, error: Optional[str], token: "_Dictation") -> None:
        """End of a dictation, however it ended. Runs once per token."""
        with self._token_lock:
            if token is not self._current:
                return
            self._current = None
        token.stopping = True  # stops the level loop
        self.hotkey_manager.reset()
        try:
            try:
                self.recorder.stop_recording()
            except Exception as e:
                error = error or str(e)
            self.writer.finish()
            error = error or self._session_error or self.recorder.stream_error
            if error:
                self._fail(error)
                self.overlay.show_error(error)
            else:
                self._set_state(STATE_IDLE)
                self.overlay.hide()
        finally:
            self._session_lock.release()

    # Type-on-stop has no VAD running, so the level loop provides its auto-stop.
    QUIET_LEVEL = 0.01

    def _start_level_monitoring(self, token: "_Dictation") -> None:
        """~30 fps while ``token`` is recording: overlay levels, dead-mic
        detection and the silence auto-stop."""
        state = {"last_loud": time.monotonic()}

        def _update():
            if token.stopping or token is not self._current:
                return
            if self.recorder.check_alive():
                # Device vanished mid-dictation: end it now rather than
                # waiting for the second hotkey press.
                self.hotkey_manager.reset()
                self._run_async(self._on_record_stop, token)
                return
            levels = self.recorder.get_levels(self.overlay.BAR_COUNT)
            now = time.monotonic()
            if max(levels, default=0.0) >= self.QUIET_LEVEL:
                state["last_loud"] = now
            elif not token.session and now - state["last_loud"] >= AUTO_STOP_SECONDS:
                self._run_async(self._auto_stop, token)
                return
            if self.overlay.is_visible:
                self.overlay.update_levels(levels)
            timer = threading.Timer(0.033, _update)
            timer.daemon = True
            timer.start()
        _update()

    # -- lifecycle -------------------------------------------------------------

    def _migrate_device(self) -> None:
        migrated = audio_devices.migrate(self.config.input_device)
        if migrated != self.config.input_device:
            self.config.input_device = migrated
            self.recorder = AudioRecorder(device_ref=migrated)
            save_config(self.config)

    def start(self) -> None:
        """Load the model and register the hotkey. Never raises; failures
        leave the app in STATE_ERROR with ``self.error`` set. Holds the
        session lock, so dictation and settings changes wait for it."""
        if self._running:
            return
        with self._session_lock:
            self._set_state(STATE_LOADING)
            uia.warm_up()
            self.overlay.start()
            gpu_runtime.cleanup()  # old runtime versions, before CUDA loads
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
        current = self._current
        if current:
            current.stopping = True
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

    def reload_config(self, new_config: AppConfig, force_model: bool = False,
                      wait: float = 0.0) -> bool:
        """Apply settings, touching only what differs from what's running.

        Never raises. Returns False, changing nothing, if a dictation (or
        another reload) holds the app for more than ``wait`` seconds.
        Anything that couldn't be applied keeps its old value and is
        described in ``self.reload_error``; ``self.config`` always describes
        what is actually running.
        """
        acquired = self._session_lock.acquire(timeout=wait) if wait else \
            self._session_lock.acquire(blocking=False)
        if not acquired:
            return False
        try:
            self._apply_config(new_config, force_model)
        finally:
            self._session_lock.release()
        return True

    def reload_in_background(self, new_config: AppConfig, force_model: bool = False,
                             on_done: Optional[Callable[[bool], None]] = None) -> None:
        """For slow changes (a model load): report "loading" now, apply on a
        thread. ``on_done(applied)`` runs afterwards."""
        self.reload_error = None
        self._set_state(STATE_LOADING)

        def _work():
            applied = self.reload_config(new_config, force_model, wait=120.0)
            if not applied:
                self.reload_error = "ShuperWhisper was busy, so that wasn't applied. Try again."
                self._set_state(STATE_IDLE if self._running else STATE_ERROR, self.error)
            if on_done:
                on_done(applied and not self.reload_error)
        self._run_async(_work)

    def _apply_config(self, new_config: AppConfig, force_model: bool = False) -> None:
        applied = AppConfig(**self.config.to_dict())
        problems: list[str] = []
        self.dictionary.load()

        if new_config.input_device != self.recorder.device_ref:
            self.recorder = AudioRecorder(device_ref=new_config.input_device)
        applied.input_device = new_config.input_device

        wanted = (new_config.model_size, new_config.compute, new_config.live_typing)
        if (force_model or wanted != self.transcriber.requested or not self.transcriber.loaded
                or self.transcriber.needs_reload_for(new_config.language)):
            self._set_state(STATE_LOADING)
            candidate = Transcriber(model_size=new_config.model_size, language=new_config.language,
                                    compute=new_config.compute, live_typing=new_config.live_typing)
            try:
                candidate.load_model()  # the old model keeps working if this fails
                self.transcriber = candidate
                applied.model_size, applied.compute, applied.live_typing = wanted
            except Exception as e:
                problems.append(f"Couldn't load the speech model: {e}")
        self.transcriber.language = new_config.language
        applied.language = new_config.language

        if new_config.hotkey != self.hotkey_manager.hotkey or not self.hotkey_manager.registered:
            candidate_keys = self._make_hotkeys(new_config.hotkey)
            try:
                if new_config.hotkey == self.hotkey_manager.hotkey:
                    self.hotkey_manager.unregister()  # same combo: free it first
                candidate_keys.register()
                self.hotkey_manager.unregister()
                self.hotkey_manager = candidate_keys
                applied.hotkey = new_config.hotkey
            except Exception as e:
                problems.append(str(e))

        self.config = applied
        self.reload_error = "; ".join(problems) or None
        if self.transcriber.loaded and self.hotkey_manager.registered:
            self._running = True
            self._set_state(STATE_IDLE)
        else:
            self._fail(self.reload_error or "ShuperWhisper isn't ready")

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
        # Windows 10 1703+: per-monitor v2 (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v1 (Windows 8.1+)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # system DPI aware
        except Exception:
            pass


def _log_to_file_when_windowed() -> None:
    """The installed app has no console; keep its output in a log file next
    to config.json so problems can be diagnosed."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    import os
    try:
        os.makedirs(config_dir(), exist_ok=True)
        path = os.path.join(config_dir(), "shuperwhisper.log")
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
            os.replace(path, path + ".old")
        log = open(path, "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log
    except OSError:
        pass


def main() -> None:
    """Entry point for the installed ``shuper-whisper`` gui-script; main.py delegates here (issue #11)."""
    multiprocessing.freeze_support()
    _log_to_file_when_windowed()
    _enable_dpi_awareness()

    if "--setup-gpu" in sys.argv:
        from .setup_window import run_setup_window
        sys.exit(run_setup_window())

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
