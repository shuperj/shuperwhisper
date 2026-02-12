"""Main application orchestrator for ShuperWhisper."""

import sys
import threading

from .audio import AudioRecorder
from .config import AppConfig, load_config
from .hotkey import HotkeyManager
from .injector import TextInjector
from .transcriber import Transcriber


class ShuperWhisperApp:
    """Wires together audio, transcription, hotkey, and text injection."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.recorder = AudioRecorder(device=config.input_device)
        self.transcriber = Transcriber(
            model_size=config.model_size,
            language=config.language,
        )
        self.injector = TextInjector()
        self.hotkey_manager = HotkeyManager(
            hotkey_str=config.hotkey,
            on_start=self._on_record_start,
            on_stop=self._on_record_stop,
        )

    def _on_record_start(self) -> None:
        self.recorder.start_recording()
        print("Recording... (release to transcribe)")

    def _on_record_stop(self) -> None:
        audio = self.recorder.stop_recording()
        print("Processing...")
        if audio is not None:
            threading.Thread(
                target=self._transcribe_and_inject,
                args=(audio,),
                daemon=True,
            ).start()
        else:
            print("No audio recorded.\n")

    def _transcribe_and_inject(self, audio) -> None:
        print("Transcribing...")
        text = self.transcriber.transcribe(audio)
        if text:
            print(f"Transcribed: {text}")
            self.injector.inject(text)
            print("Pasted!\n")
        else:
            print("No speech detected.\n")

    def run(self) -> None:
        """Start the application. Blocks until Ctrl+C."""
        # Load the model
        self.transcriber.load_model()

        # Print device info
        if self.config.input_device is not None:
            print(f"Input device: {self.config.input_device}")
        else:
            print(f"Input device: {AudioRecorder.get_default_device_name()} (default)")
        print("Run with --list-devices to see all available devices\n")

        print(f"Hold [{self.config.hotkey}] to record, release to transcribe.")
        print("Press Ctrl+C to exit.\n")

        # Start audio stream
        self.recorder.open_stream()

        # Register hotkey handlers
        self.hotkey_manager.register()

        try:
            self.hotkey_manager.wait()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.hotkey_manager.unregister()
            self.recorder.close_stream()


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
