"""Main application orchestrator for ShuperWhisper."""

import sys
import threading
from typing import Callable, Optional

from .audio import AudioRecorder
from .config import AppConfig, load_config
from .hotkey import HotkeyManager
from .injector import TextInjector
from .transcriber import Transcriber

# Application states
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_LOADING = "loading"


class ShuperWhisperApp:
    """Wires together audio, transcription, hotkey, and text injection."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._state_callback: Optional[Callable[[str], None]] = None
        self._running = False

        self.recorder = AudioRecorder(device=config.input_device)
        self.transcriber = Transcriber(
            model_size=config.model_size,
            language=config.language,
        )
        self.injector = TextInjector(
            smart_spacing=config.smart_spacing,
            bullet_mode=config.bullet_mode,
            email_mode=config.email_mode,
        )
        self.hotkey_manager = HotkeyManager(
            hotkey_str=config.hotkey,
            on_start=self._on_record_start,
            on_stop=self._on_record_stop,
        )

    def set_state_callback(self, callback: Callable[[str], None]) -> None:
        """Set a callback for state changes (idle, recording, processing, loading)."""
        self._state_callback = callback

    def _set_state(self, state: str) -> None:
        if self._state_callback:
            self._state_callback(state)

    def _on_record_start(self) -> None:
        self.recorder.start_recording()
        self._set_state(STATE_RECORDING)
        print("Recording... (release to transcribe)")

    def _on_record_stop(self) -> None:
        audio = self.recorder.stop_recording()
        self._set_state(STATE_PROCESSING)
        print("Processing...")
        if audio is not None:
            threading.Thread(
                target=self._transcribe_and_inject,
                args=(audio,),
                daemon=True,
            ).start()
        else:
            print("No audio recorded.\n")
            self._set_state(STATE_IDLE)

    def _transcribe_and_inject(self, audio) -> None:
        print("Transcribing...")
        text = self.transcriber.transcribe(audio)
        if text:
            print(f"Transcribed: {text}")
            self.injector.inject(text)
            print("Pasted!\n")
        else:
            print("No speech detected.\n")
        self._set_state(STATE_IDLE)

    def start(self) -> None:
        """Start the application in non-blocking mode.

        Loads the model, opens the audio stream, and registers hotkeys.
        Does NOT block the calling thread.
        """
        if self._running:
            return

        self._set_state(STATE_LOADING)

        # Load the model
        self.transcriber.load_model()

        # Print device info
        if self.config.input_device is not None:
            print(f"Input device: {self.config.input_device}")
        else:
            print(f"Input device: {AudioRecorder.get_default_device_name()} (default)")

        print(f"Hold [{self.config.hotkey}] to record, release to transcribe.")

        # Start audio stream
        self.recorder.open_stream()

        # Register hotkey handlers
        self.hotkey_manager.register()

        self._running = True
        self._set_state(STATE_IDLE)

    def shutdown(self) -> None:
        """Stop the application cleanly."""
        if not self._running:
            return
        self.hotkey_manager.unregister()
        self.recorder.close_stream()
        self._running = False
        print("ShuperWhisper stopped.")

    def reload_config(self, new_config: AppConfig) -> None:
        """Apply a new configuration, restarting subsystems as needed."""
        needs_restart = (
            new_config.model_size != self.config.model_size
            or new_config.hotkey != self.config.hotkey
            or new_config.input_device != self.config.input_device
            or new_config.language != self.config.language
        )
        self.config = new_config
        # Always update injector settings (no restart needed)
        self.injector.smart_spacing = new_config.smart_spacing
        self.injector.bullet_mode = new_config.bullet_mode
        self.injector.email_mode = new_config.email_mode
        if needs_restart and self._running:
            self.shutdown()
            self.transcriber = Transcriber(
                model_size=new_config.model_size,
                language=new_config.language,
            )
            self.recorder = AudioRecorder(device=new_config.input_device)
            self.hotkey_manager = HotkeyManager(
                hotkey_str=new_config.hotkey,
                on_start=self._on_record_start,
                on_stop=self._on_record_stop,
            )
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self) -> None:
        """Start the application. Blocks until Ctrl+C.

        Legacy entry point for console mode.
        """
        self.start()
        try:
            self.hotkey_manager.wait()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.shutdown()


def list_devices() -> None:
    """Print available audio input devices and exit."""
    print("Available audio input devices:\n")
    for dev in AudioRecorder.list_devices():
        default = " (DEFAULT)" if dev["is_default"] else ""
        print(f"  [{dev['index']}] {dev['name']}{default}")
        print(
            f"      Channels: {dev['channels']}, Sample Rate: {dev['sample_rate']} Hz"
        )
    print("\nSet input_device in config.json to the device index or name.")
