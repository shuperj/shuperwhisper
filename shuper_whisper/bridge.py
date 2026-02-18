"""pywebview JS API bridge — all Python↔React communication goes through here."""

import json
import keyboard
import time
import threading


class WindowAPI:
    """API class exposed to JavaScript via pywebview.api.

    Every public method becomes callable from React as:
        await window.pywebview.api.method_name(args)
    """

    def __init__(self, window=None):
        self._window = window
        self._capturing = False
        self._app = None  # ShuperWhisperApp, set via set_app_instance()

    def set_app_instance(self, app) -> None:
        """Wire the ShuperWhisperApp reference (called by TrayController)."""
        self._app = app

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def close_window(self):
        """Close the current settings window."""
        if self._window:
            self._window.destroy()

    # ------------------------------------------------------------------
    # Hotkey capture
    # ------------------------------------------------------------------

    def capture_hotkey(self, timeout=10):
        """Capture a hotkey combination from the user.

        Returns a string like "ctrl+shift+space" or None if timeout/cancelled.
        """
        if self._capturing:
            return None

        self._capturing = True
        modifiers = set()
        trigger_key = None
        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                event = keyboard.read_event(suppress=True)

                if event.event_type == 'down':
                    key = event.name.lower()

                    if key in ('ctrl', 'shift', 'alt', 'windows', 'win', 'super',
                              'left ctrl', 'right ctrl', 'left shift', 'right shift',
                              'left alt', 'right alt', 'left windows', 'right windows'):
                        if key in ('win', 'super', 'left windows', 'right windows'):
                            modifiers.add('windows')
                        elif key in ('left ctrl', 'right ctrl'):
                            modifiers.add('ctrl')
                        elif key in ('left shift', 'right shift'):
                            modifiers.add('shift')
                        elif key in ('left alt', 'right alt'):
                            modifiers.add('alt')
                        else:
                            modifiers.add(key)
                    elif key == 'esc':
                        return None
                    else:
                        trigger_key = key
                        break

            if trigger_key:
                parts = sorted(list(modifiers)) + [trigger_key]
                return '+'.join(parts)
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
        """List audio input devices."""
        try:
            from .audio import AudioRecorder
            return AudioRecorder.list_devices()
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
        """Validate, save, and apply configuration. Returns {success, config}."""
        from .config import AppConfig, save_config

        try:
            config = AppConfig(
                hotkey=data.get('hotkey', 'ctrl+shift+space'),
                model_size=data.get('model_size', 'base'),
                input_device=data.get('input_device'),
                language=data.get('language', 'en'),
                smart_spacing=data.get('smart_spacing', True),
                bullet_mode=data.get('bullet_mode', False),
                email_mode=data.get('email_mode', False),
                hotkey_mode=data.get('hotkey_mode', 'hold'),
                format_mode=data.get('format_mode', 'normal'),
                email_tone=data.get('email_tone', 3),
                prompt_detail=data.get('prompt_detail', 3),
                overlay_position=data.get('overlay_position', 'top_center'),
                accent_color=data.get('accent_color', '#ff4466'),
                bg_color=data.get('bg_color', '#1a1a2e'),
            )
            config.validate()
            save_config(config)

            if self._app:
                self._app.reload_config(config)

            return {'success': True, 'config': config.to_dict()}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_config_options(self):
        """Return available options for config dropdowns."""
        from .config import (
            AppConfig,
            SUPPORTED_LANGUAGES,
            VALID_HOTKEY_MODES,
            VALID_FORMAT_MODES,
            VALID_OVERLAY_POSITIONS,
            FORMAT_MODE_LABELS,
        )
        return {
            'models': list(AppConfig.VALID_MODELS),
            'languages': SUPPORTED_LANGUAGES,
            'hotkey_modes': list(VALID_HOTKEY_MODES),
            'format_modes': {key: FORMAT_MODE_LABELS[key] for key in VALID_FORMAT_MODES},
            'overlay_positions': list(VALID_OVERLAY_POSITIONS),
        }

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
