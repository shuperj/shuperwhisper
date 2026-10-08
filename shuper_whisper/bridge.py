"""pywebview JS API bridge — all Python↔React communication goes through here."""

import json
import time
import threading

from . import autostart, gpu_runtime, system_theme
from .audio import AudioRecorder
from .transcriber import gpu_name

_MODEL_LABELS = {"large-v3-turbo": "Large v3 Turbo", "base.en": "Base (English)"}
# One GPU download at a time, shared by every settings window.
_gpu_setup = gpu_runtime.GpuSetup()
from ._win32_keys import (
    MODIFIER_VK_MAP,
    VK_MAP,
    VK_TO_NAME,
    _ALL_MODIFIER_VKS,
    is_key_down,
)


class WindowAPI:
    """API class exposed to JavaScript via pywebview.api.

    Every public method becomes callable from React as:
        await window.pywebview.api.method_name(args)
    """

    def __init__(self, window=None):
        self._window = window
        self._capturing = False
        self._app = None  # ShuperWhisperApp, set via set_app_instance()
        self._mic_test = None
        self._mic_lock = threading.Lock()

    def set_app_instance(self, app) -> None:
        """Wire the ShuperWhisperApp reference (called by TrayController)."""
        self._app = app

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def close_window(self):
        """Close the current settings window."""
        self.stop_mic_test()
        if self._window:
            self._window.destroy()

    # ------------------------------------------------------------------
    # Hotkey capture
    # ------------------------------------------------------------------

    def capture_hotkey(self, timeout=10):
        """Capture a hotkey combination from the user.

        Polls GetAsyncKeyState to detect which keys are pressed.
        Returns a string like "ctrl+shift+space" or None if timeout/cancelled.
        """
        if self._capturing:
            return None

        self._capturing = True
        start_time = time.time()

        # Modifier VK -> canonical name
        _mod_vk_to_name = {
            0xA2: "ctrl", 0xA3: "ctrl",      # L/R Control
            0xA0: "shift", 0xA1: "shift",    # L/R Shift
            0xA4: "alt", 0xA5: "alt",        # L/R Alt (Menu)
            0x5B: "windows", 0x5C: "windows", # L/R Win
        }

        try:
            # Wait for any previously held keys to be released first
            time.sleep(0.2)

            while time.time() - start_time < timeout:
                # Check for escape
                if is_key_down(VK_MAP.get("esc", 0x1B)):
                    return None

                # Collect currently pressed modifiers
                modifiers = set()
                for vk, name in _mod_vk_to_name.items():
                    if is_key_down(vk):
                        modifiers.add(name)

                # Scan for a non-modifier trigger key
                trigger_key = None
                for vk, name in VK_TO_NAME.items():
                    if vk in _ALL_MODIFIER_VKS:
                        continue
                    if vk == 0x1B:  # Skip escape (handled above)
                        continue
                    if is_key_down(vk):
                        trigger_key = name
                        break

                if trigger_key:
                    parts = sorted(list(modifiers)) + [trigger_key]
                    return "+".join(parts)

                time.sleep(0.05)  # 50ms polling

            return None

        except Exception as e:
            print(f"Error capturing hotkey: {e}")
            return None
        finally:
            self._capturing = False

    # ------------------------------------------------------------------
    # Audio devices
    # ------------------------------------------------------------------

    def get_devices(self):
        """List input devices (re-scanned, so newly plugged devices show up)."""
        try:
            from . import audio_devices
            audio_devices.refresh()
            return [d.to_dict() for d in audio_devices.list_input_devices()]
        except Exception as e:
            print(f"Error getting devices: {e}")
            return []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config(self):
        """Load and return current configuration as a dict."""
        from .config import load_config
        return load_config().to_dict()

    def save_config(self, data):
        """Validate, check the mic, apply, then save what's actually running.

        ``data`` may be a partial patch; it's merged with the saved config.
        A change that needs a model load runs in the background (seconds);
        the page polls get_status() until the state leaves "loading", and
        reads ``reload_error`` for anything that couldn't be applied.
        Returns {success, config, loading?} or {success: False, error, config?}.
        """
        from . import audio_devices
        from .config import _CONFIG_FIELDS, AppConfig, load_config, save_config

        try:
            current = load_config()
            merged = {**current.to_dict(), **(data or {})}
            config = AppConfig(**{k: merged[k] for k in _CONFIG_FIELDS if k in merged})
            config.validate()
            if config.input_device != current.input_device:
                problem = audio_devices.check(config.input_device)
                if problem:
                    return {'success': False, 'error': f"Can't use that microphone: {problem}"}
            app = self._app
            if not app:
                save_config(config)
                return {'success': True, 'config': config.to_dict()}
            if app.state == "loading":
                return {'success': False, 'error': 'Still loading the speech model. Try again in a moment.'}
            if app.busy:
                return {'success': False, 'error': 'Finish dictating first, then try again.'}
            # Decide by what's running, not by what's on disk.
            wanted = app.model_wanted(config)
            if (wanted != app.transcriber.requested or not app.transcriber.loaded
                    or app.transcriber.needs_reload_for(config.language)):
                app.reload_in_background(config, on_done=lambda ok: save_config(app.config))
                return {'success': True, 'loading': True, 'config': config.to_dict()}
            if not app.reload_config(config):
                return {'success': False, 'error': 'Finish dictating first, then try again.'}
            save_config(app.config)
            problem = app.reload_error or app.error
            if problem:
                return {'success': False, 'error': problem, 'config': app.config.to_dict()}
            return {'success': True, 'config': app.config.to_dict()}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_config_options(self):
        """Return available options for config dropdowns."""
        from .config import AppConfig, SUPPORTED_LANGUAGES
        return {
            'models': list(AppConfig.VALID_MODELS),
            'languages': SUPPORTED_LANGUAGES,
        }

    # ------------------------------------------------------------------
    # Status and system info
    # ------------------------------------------------------------------

    def get_status(self):
        if not self._app:
            return {'state': 'idle', 'error': None, 'reload_error': None,
                    'efficient': False, 'efficiency_reason': ''}
        return {'state': self._app.state, 'error': self._app.error,
                'reload_error': self._app.reload_error,
                'efficient': bool(self._app.efficient), 'efficiency_reason': self._app.efficiency_reason}

    def get_system_info(self):
        compute = "Not loaded"
        if self._app and self._app.transcriber.device:
            size = self._app.transcriber.model_size
            label = _MODEL_LABELS.get(size, size.capitalize())
            where = (gpu_name() or "NVIDIA GPU") if self._app.transcriber.device == "cuda" else "CPU"
            compute = f"{label} on {where}"
        return {
            'dark': system_theme.apps_use_dark(),
            'accent': system_theme.accent_colors(),
            'compute': compute,
        }

    # ------------------------------------------------------------------
    # Mic test (level meter on the Microphone card)
    # ------------------------------------------------------------------

    def start_mic_test(self, device_ref):
        with self._mic_lock:  # JS calls run on their own threads; a double-click mustn't leak a stream
            self._stop_mic_test_locked()
            if self._app and self._app.state == "loading":
                return {'success': False, 'error': 'Still loading the speech model. Try again in a moment.'}
            if self._app and self._app.busy:
                return {'success': False, 'error': 'Finish dictating first, then try again.'}
            recorder = AudioRecorder(device_ref=device_ref)
            try:
                recorder.start_recording()
            except Exception as e:
                return {'success': False, 'error': str(e)}
            self._mic_test = recorder
            return {'success': True}

    def get_mic_level(self):
        recorder = self._mic_test
        if not recorder:
            return 0.0
        return float(recorder.get_levels(1)[-1])

    def stop_mic_test(self):
        with self._mic_lock:
            self._stop_mic_test_locked()

    def _stop_mic_test_locked(self):
        recorder, self._mic_test = self._mic_test, None
        if recorder:
            try:
                recorder.stop_recording()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # GPU acceleration
    # ------------------------------------------------------------------

    def get_gpu_status(self):
        return {
            'gpu': gpu_name(),
            'installed': gpu_runtime.installed(),
            'active': bool(self._app and self._app.transcriber.device == 'cuda'),
        }

    def setup_gpu(self):
        def _activate():
            # Before "done" is reported: load the model on the GPU now, waiting
            # out a dictation if one is running.
            if self._app:
                self._app.reload_config(self._app.config, force_model=True, wait=120.0)
        _gpu_setup.start(on_installed=_activate)
        return {'success': True}

    def get_gpu_setup_progress(self):
        return _gpu_setup.progress.to_dict()

    def cancel_gpu_setup(self):
        _gpu_setup.cancel()

    # ------------------------------------------------------------------
    # Autostart
    # ------------------------------------------------------------------

    def get_autostart(self):
        """Return whether autostart is currently enabled."""
        return autostart.is_enabled()

    def set_autostart(self, enabled):
        """Enable or disable autostart. Returns the new state."""
        if enabled:
            autostart.enable()
        else:
            autostart.disable()
        return autostart.is_enabled()

    # ------------------------------------------------------------------
    # Dictionary
    # ------------------------------------------------------------------

    def get_dictionary(self):
        """Return all dictionary entries as a list of dicts."""
        if self._app and hasattr(self._app, 'dictionary'):
            return [
                {'word': e.word, 'phonetic': e.phonetic, 'trained': e.trained}
                for e in self._app.dictionary.entries
            ]
        return []

    def add_word(self, word, phonetic=''):
        """Add a word to the dictionary. Returns the entry dict."""
        word = (word or '').strip()
        phonetic = (phonetic or '').strip()
        if not word:
            return {'success': False, 'error': 'Word is required'}

        if self._app and hasattr(self._app, 'dictionary'):
            entry = self._app.dictionary.add(word, phonetic)
            return {
                'word': entry.word,
                'phonetic': entry.phonetic,
                'trained': entry.trained,
            }
        return {'success': False, 'error': 'Dictionary not available'}

    def remove_word(self, word):
        """Remove a word from the dictionary. Returns True on success."""
        if self._app and hasattr(self._app, 'dictionary'):
            return self._app.dictionary.remove(word)
        return False

    def update_word(self, old_word, new_word, phonetic=''):
        """Update an existing dictionary entry's word and/or phonetic hint."""
        old_word = (old_word or '').strip()
        new_word = (new_word or '').strip()
        phonetic = (phonetic or '').strip()
        if not old_word or not new_word:
            return {'success': False, 'error': 'Both old and new word are required'}

        if self._app and hasattr(self._app, 'dictionary'):
            result = self._app.dictionary.update(old_word, new_word, phonetic)
            if result:
                return {'success': True}
            return {'success': False, 'error': 'Word not found'}
        return {'success': False, 'error': 'Dictionary not available'}

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip punctuation and whitespace for comparison."""
        import re
        return re.sub(r'[^\w\s]', '', text).strip().lower()

    def train_word(self, word):
        """Record 3 rounds, learn what Whisper hears, auto-build phonetic hint.

        Instead of pass/fail validation, training *teaches* the dictionary
        by collecting Whisper's natural transcription of the user's speech.
        If Whisper doesn't already recognize the word, the most common
        transcription becomes the phonetic hint so future dictation maps
        correctly (e.g. Whisper hears "mackinaw" → phonetic hint "mackinaw"
        → initial_prompt includes "Mackinac (mackinaw)").
        """
        word = (word or '').strip()
        if not word:
            return {'success': False, 'error': 'Word is required'}

        if not self._app:
            return {'success': False, 'error': 'App not available'}

        if not hasattr(self._app, 'recorder') or not hasattr(self._app, 'transcriber'):
            return {'success': False, 'error': 'Recorder or transcriber not available'}

        # Training records through the app's microphone: never alongside a
        # dictation (or another training run).
        lock = getattr(self._app, '_session_lock', None)
        if lock is not None and not lock.acquire(blocking=False):
            return {'success': False, 'error': 'Finish dictating first, then try again.'}
        try:
            return self._train(word)
        finally:
            if lock is not None:
                lock.release()

    def _train(self, word):

        def _push(data):
            """Push a training status event to React."""
            if self._window:
                try:
                    js = f"window.__onTrainingStatus({json.dumps(data)})"
                    self._window.evaluate_js(js)
                except Exception:
                    pass

        total_rounds = 3
        results = []
        transcriptions = []

        # Build dictionary hints to bias transcription
        initial_prompt = None
        hotwords = None
        if hasattr(self._app, 'dictionary'):
            initial_prompt = self._app.dictionary.get_initial_prompt() or None
            hotwords = self._app.dictionary.get_hotwords() or None

        try:
            for round_num in range(1, total_rounds + 1):
                _push({
                    'status': 'recording',
                    'word': word,
                    'round': round_num,
                    'totalRounds': total_rounds,
                })

                recorder = self._app.recorder
                recorder.start_recording()
                time.sleep(3)
                audio_data = recorder.stop_recording()

                _push({
                    'status': 'transcribing',
                    'word': word,
                    'round': round_num,
                    'totalRounds': total_rounds,
                })

                transcriber = self._app.transcriber
                raw = transcriber.transcribe(
                    audio_data,
                    initial_prompt=initial_prompt,
                    hotwords=hotwords,
                ).strip()
                normalized = self._normalize(raw)

                is_match = normalized == self._normalize(word)
                transcriptions.append(normalized)

                results.append({
                    'round': round_num,
                    'transcribed': normalized,
                    'success': is_match,
                })

                _push({
                    'status': 'round_done',
                    'word': word,
                    'round': round_num,
                    'totalRounds': total_rounds,
                    'transcribed': normalized,
                    'roundSuccess': is_match,
                })

                # Pause between rounds for user to see result
                if round_num < total_rounds:
                    time.sleep(1)

            # Determine if Whisper already recognizes the word
            match_count = sum(
                1 for t in transcriptions if t == self._normalize(word)
            )
            already_recognized = match_count >= 2

            # Auto-build phonetic hint from what Whisper actually heard
            learned_hint = None
            if not already_recognized and hasattr(self._app, 'dictionary'):
                # Find the most common non-matching transcription
                from collections import Counter
                misheard = [
                    t for t in transcriptions
                    if t and t != self._normalize(word)
                ]
                if misheard:
                    learned_hint = Counter(misheard).most_common(1)[0][0]
                    self._app.dictionary.add(word, learned_hint)

            # Always mark as trained — the point is collecting data
            if hasattr(self._app, 'dictionary'):
                self._app.dictionary.mark_trained(word)

            _push({
                'status': 'done',
                'word': word,
                'success': True,
                'alreadyRecognized': already_recognized,
                'learnedHint': learned_hint,
                'matchCount': match_count,
                'totalRounds': total_rounds,
                'results': results,
            })

            return {
                'success': True,
                'alreadyRecognized': already_recognized,
                'learnedHint': learned_hint,
                'matchCount': match_count,
                'totalRounds': total_rounds,
                'results': results,
            }

        except Exception as e:
            _push({'status': 'error', 'error': str(e)})
            return {'success': False, 'error': str(e)}
