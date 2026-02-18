"""Main application orchestrator for ShuperWhisper."""

import threading
from typing import Callable, Optional

from .audio import AudioRecorder
from .config import AppConfig, load_config
from .dictionary import WordDictionary
from .formatter import TextFormatter
from .hotkey import HotkeyManager
from .injector import TextInjector
from .overlay import RecordingOverlay
from .transcriber import Transcriber

# Application states
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_LOADING = "loading"


class ShuperWhisperApp:
    """Wires together audio, transcription, hotkey, overlay, formatting, and text injection."""

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
            mode=config.hotkey_mode,
        )
        self.formatter = TextFormatter()
        self.dictionary = WordDictionary()
        self.overlay = RecordingOverlay(
            position=config.overlay_position,
            accent_color=config.accent_color,
            bg_color=config.bg_color,
        )
        self._current_format_mode = config.format_mode
        self._level_timer: Optional[threading.Timer] = None

    def set_state_callback(self, callback: Callable[[str], None]) -> None:
        """Set a callback for state changes (idle, recording, processing, loading)."""
        self._state_callback = callback

    def _set_state(self, state: str) -> None:
        if self._state_callback:
            self._state_callback(state)

    def _on_record_start(self) -> None:
        self.recorder.start_recording()
        self._set_state(STATE_RECORDING)
        self._current_format_mode = self.config.format_mode

        # Show overlay (always in "toggle" mode for format controls)
        self.overlay.show(
            mode="toggle",
            format_mode=self._current_format_mode,
        )

        # Start feeding audio levels to overlay
        self._start_level_monitoring()

        # Register arrow keys for format cycling
        self.hotkey_manager.register_arrow_keys(
            on_up=lambda: self.overlay.cycle_format_mode(-1),
            on_down=lambda: self.overlay.cycle_format_mode(1),
        )

        print("Recording... (release quick = hold mode, release slow = toggle mode)")

    def _on_record_stop(self) -> None:
        # Clean up arrow keys
        self.hotkey_manager.unregister_arrow_keys()

        # Stop level monitoring
        self._stop_level_monitoring()

        audio = self.recorder.stop_recording()
        self._set_state(STATE_PROCESSING)
        self.overlay.show_processing()

        # Capture format mode from overlay (user may have cycled it)
        format_mode = self.overlay.format_mode

        print("Processing...")
        if audio is not None:
            threading.Thread(
                target=self._transcribe_and_inject,
                args=(audio, format_mode),
                daemon=True,
            ).start()
        else:
            print("No audio recorded.\n")
            self.overlay.hide()
            self._set_state(STATE_IDLE)

    def _transcribe_and_inject(self, audio, format_mode: str) -> None:
        # Build initial prompt and hotwords from dictionary
        initial_prompt = self.dictionary.get_initial_prompt() or None
        hotwords = self.dictionary.get_hotwords() or None

        print("Transcribing...")
        text = self.transcriber.transcribe(
            audio,
            initial_prompt=initial_prompt,
            hotwords=hotwords,
        )

        if text:
            print(f"Transcribed: {text}")

            # Apply format mode if not normal
            if format_mode != "normal":
                formatted = self.formatter.format_text(
                    text,
                    format_mode,
                    email_tone=self.config.email_tone,
                    prompt_detail=self.config.prompt_detail,
                )
                if formatted:
                    print(f"Formatted ({format_mode}): {formatted}")
                    text = formatted

            self.injector.inject(text)
            print("Pasted!\n")
        else:
            print("No speech detected.\n")

        self.overlay.hide()
        self._set_state(STATE_IDLE)

    def _start_level_monitoring(self) -> None:
        """Feed audio levels to overlay at ~30fps."""
        def _update():
            if self._running and self.overlay.is_visible:
                levels = self.recorder.get_levels(self.overlay.BAR_COUNT)
                self.overlay.update_levels(levels)
                self._level_timer = threading.Timer(0.033, _update)
                self._level_timer.daemon = True
                self._level_timer.start()
        _update()

    def _stop_level_monitoring(self) -> None:
        if self._level_timer:
            self._level_timer.cancel()
            self._level_timer = None

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

        print(f"Hotkey: [{self.config.hotkey}] | Mode: Smart (quick tap = toggle, hold = hold)")

        # Start audio stream
        self.recorder.open_stream()

        # Register hotkey handlers
        self.hotkey_manager.register()

        # Start overlay thread
        self.overlay.start()

        self._running = True
        self._set_state(STATE_IDLE)

    def shutdown(self) -> None:
        """Stop the application cleanly."""
        if not self._running:
            return
        self._stop_level_monitoring()
        self.hotkey_manager.unregister()
        self.recorder.close_stream()
        self.overlay.destroy()
        self._running = False
        print("ShuperWhisper stopped.")

    def reload_config(self, new_config: AppConfig) -> None:
        """Apply a new configuration, restarting subsystems as needed."""
        needs_restart = (
            new_config.model_size != self.config.model_size
            or new_config.hotkey != self.config.hotkey
            or new_config.input_device != self.config.input_device
            or new_config.language != self.config.language
            or new_config.hotkey_mode != self.config.hotkey_mode
        )
        self.config = new_config

        # Always update injector settings (no restart needed)
        self.injector.smart_spacing = new_config.smart_spacing
        self.injector.bullet_mode = new_config.bullet_mode
        self.injector.email_mode = new_config.email_mode
        self._current_format_mode = new_config.format_mode

        # Update overlay position and colors
        self.overlay.set_position(new_config.overlay_position)
        self.overlay.set_colors(new_config.accent_color, new_config.bg_color)

        # Reload dictionary
        self.dictionary.load()

        if needs_restart and self._running:
            self.shutdown()
            self.recorder = AudioRecorder(device=new_config.input_device)
            self.transcriber = Transcriber(
                model_size=new_config.model_size,
                language=new_config.language,
            )
            self.hotkey_manager = HotkeyManager(
                hotkey_str=new_config.hotkey,
                on_start=self._on_record_start,
                on_stop=self._on_record_stop,
                mode=new_config.hotkey_mode,
            )
            self.overlay = RecordingOverlay(
                position=new_config.overlay_position,
                accent_color=new_config.accent_color,
                bg_color=new_config.bg_color,
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
