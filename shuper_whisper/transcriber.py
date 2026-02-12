"""Speech-to-text transcription using faster-whisper."""

from typing import Optional

import numpy as np
from faster_whisper import WhisperModel


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
        """Load the Whisper model. Call once at startup."""
        print(
            f"Loading Whisper model: {self._model_size} ({self._device}, {self._compute_type})"
        )
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        print("Model loaded!")

    def transcribe(self, audio: np.ndarray, beam_size: int = 5) -> str:
        """Transcribe audio data to text.

        Args:
            audio: Float32 numpy array of audio samples at 16kHz mono.
            beam_size: Beam search width.

        Returns:
            Transcribed text, or empty string if no speech detected.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        lang = None if self._language == "auto" else self._language
        segments, info = self._model.transcribe(
            audio,
            beam_size=beam_size,
            language=lang,
        )
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
