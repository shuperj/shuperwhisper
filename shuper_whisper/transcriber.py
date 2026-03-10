"""Speech-to-text transcription using faster-whisper."""

import os
import sys
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel


def _bundled_model_path(model_size: str) -> str | None:
    """Return the path to a bundled model if it exists alongside the exe."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "model", model_size)
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "model.bin")):
        return path
    return None


class Transcriber:
    """Wraps the faster-whisper WhisperModel for speech-to-text."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
    ):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model: Optional[WhisperModel] = None

    def load_model(self) -> None:
        """Load the Whisper model. Call once at startup.

        Checks for a bundled model directory first (model/<size>/), falling
        back to the standard Hugging Face download.
        """
        bundled = _bundled_model_path(self._model_size)
        model_source = bundled or self._model_size
        if bundled:
            print(f"Loading bundled Whisper model: {bundled}")
        else:
            print(
                f"Loading Whisper model: {self._model_size} "
                f"({self._device}, {self._compute_type})"
            )
        self._model = WhisperModel(
            model_source,
            device=self._device,
            compute_type=self._compute_type,
        )
        print("Model loaded!")

    def transcribe(
        self,
        audio: np.ndarray,
        beam_size: int = 5,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
    ) -> str:
        """Transcribe audio data to text.

        Args:
            audio: Float32 numpy array of audio samples at 16kHz mono.
            beam_size: Beam search width.
            initial_prompt: Optional prompt to bias transcription vocabulary.
            hotwords: Optional comma-separated hotwords for recognition bias.

        Returns:
            Transcribed text, or empty string if no speech detected.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        lang = None if self._language == "auto" else self._language

        kwargs = {
            "beam_size": beam_size,
            "language": lang,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        if hotwords:
            kwargs["hotwords"] = hotwords

        segments, info = self._model.transcribe(audio, **kwargs)
        text = " ".join(segment.text for segment in segments).strip()
        return text

    @property
    def model_size(self) -> str:
        return self._model_size

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = value
